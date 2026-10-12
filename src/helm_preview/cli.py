"""Click CLI entry point for helm-preview."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import click
import yaml

from helm_preview.analysis.ownership import OwnershipInfo, detect_ownership
from helm_preview.analysis.risk import RiskAnnotation, RiskLevel, assess_risk
from helm_preview.core.helm import dry_run_upgrade, get_manifest
from helm_preview.core.kubectl import current_namespace, get_live_object, server_side_dry_run
from helm_preview.core.runner import RunError
from helm_preview.diff.engine import ChangeRecord, diff_all
from helm_preview.output.json_out import render_json
from helm_preview.output.terminal import render_terminal
from helm_preview.parser.manifest import (
    Resource,
    ResourcePair,
    parse_multi_doc,
    pair_resources,
)

if TYPE_CHECKING:
    from helm_preview.crd.report import CrdReport


@click.group()
@click.version_option()
def main() -> None:
    """helm-preview: Semantic, noise-filtered, risk-aware diffs for Helm upgrades."""


@main.command()
@click.argument("release")
@click.argument("chart")
@click.option("-n", "--namespace", default=None, help="Kubernetes namespace")
@click.option("-f", "--values", multiple=True, help="Values file(s)")
@click.option("--set", "set_values", multiple=True, help="Set values (key=val)")
@click.option("--version", default=None, help="Chart version")
@click.option("--server-side", is_flag=True, help="Truth-diff via server-side dry-run")
@click.option("--show-all", is_flag=True, help="Disable noise filtering")
@click.option(
    "-o", "--output", "output_format",
    type=click.Choice(["terminal", "json"]),
    default="terminal",
    help="Output format",
)
@click.option("--context", default=None, type=int, hidden=True, help="Deprecated: has no effect")
@click.option("--ignore-path", multiple=True, help="Additional dot-paths to ignore")
@click.option("--kubeconfig", default=None, help="Path to kubeconfig")
@click.option("--kube-context", default=None, help="Kubernetes context to use")
@click.option("--no-color", is_flag=True, help="Disable colored output")
@click.option("--risk-only", is_flag=True, help="Only show WARNING/DANGER changes")
@click.option("--check-crds", is_flag=True, help="Enable CRD analysis")
@click.option(
    "--crd-policy",
    type=click.Choice(["ignore", "warn", "fail"]),
    default="warn",
    help="CRD policy: ignore | warn | fail (default: warn)",
)
def diff(
    release: str,
    chart: str,
    namespace: str | None,
    values: tuple[str, ...],
    set_values: tuple[str, ...],
    version: str | None,
    server_side: bool,
    show_all: bool,
    output_format: str,
    context: int | None,
    ignore_path: tuple[str, ...],
    kubeconfig: str | None,
    kube_context: str | None,
    no_color: bool,
    risk_only: bool,
    check_crds: bool,
    crd_policy: str,
) -> None:
    """Preview the diff of a Helm upgrade."""
    kube_opts = {
        "kubeconfig": kubeconfig,
        "kube_context": kube_context,
    }

    try:
        ns = namespace or current_namespace(**kube_opts)
        if context is not None:
            click.echo("Warning: --context is deprecated and has no effect", err=True)

        # 1. Fetch live manifests
        live_yaml = get_manifest(release, ns, **kube_opts)
        live_resources = parse_multi_doc(live_yaml, default_namespace=ns)

        # 2. Render upgrade (dry-run)
        upgrade_yaml = dry_run_upgrade(
            release, chart, ns,
            values_files=list(values),
            set_values=list(set_values),
            version=version,
            **kube_opts,
        )
        upgrade_resources = parse_multi_doc(upgrade_yaml, default_namespace=ns)

        # 3. Optional: server-side truth diff. Both sides must come from the
        # API server, otherwise server-populated defaults show up as changes.
        warnings: list[str] = []
        if server_side:
            live_resources = _fetch_live_objects(live_resources, warnings, **kube_opts)
            upgrade_resources = _apply_server_side(upgrade_resources, warnings, **kube_opts)

        # 4. Parse & pair
        pairs = pair_resources(live_resources, upgrade_resources)

        # 4b. If --check-crds, separate CRD pairs from non-CRD pairs
        crd_report = None
        if check_crds:
            non_crd_pairs = [p for p in pairs if not _is_crd_pair(p)]
            crd_report = _run_crd_analysis(
                upgrade_resources, chart, crd_policy, release, **kube_opts
            )
        else:
            non_crd_pairs = pairs

        # 5-6. Filter, normalize & diff
        change_records = diff_all(
            non_crd_pairs,
            show_all=show_all,
            extra_ignores=list(ignore_path) if ignore_path else None,
        )

        # 7. Risk analysis + ownership
        risk_results = assess_risk(change_records)
        full_results: list[tuple[ChangeRecord, list[RiskAnnotation], OwnershipInfo | None]] = []
        for change, risk_annotations in risk_results:
            # Detect ownership from the new resource (or old if removed)
            resource = _find_resource(change, live_resources, upgrade_resources)
            ownership = detect_ownership(resource) if resource else None
            full_results.append((change, risk_annotations, ownership))

        # Unchanged = identical, or different only in filtered-out noise
        total_unchanged = len(non_crd_pairs) - len(change_records)

        if risk_only:
            full_results = [
                r for r in full_results
                if any(a.level in (RiskLevel.WARNING, RiskLevel.DANGER) for a in r[1])
            ]

        # Warnings go to stderr so JSON on stdout stays machine-readable
        for warning in warnings:
            click.echo(f"Warning: {warning}", err=True)

        # 8. Output
        if output_format == "json":
            click.echo(render_json(
                full_results, total_unchanged=total_unchanged, crd_report=crd_report
            ))
        else:
            render_terminal(
                full_results,
                no_color=no_color,
                risk_only=risk_only,
                crd_report=crd_report,
            )

        # Exit non-zero if CRD policy blocks
        if crd_report and crd_report.policy_result and crd_report.policy_result.blocked:
            sys.exit(1)

    except RunError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def _is_crd_pair(pair: ResourcePair) -> bool:
    """Check if a resource pair involves a CRD."""
    res = pair.new or pair.old
    return res is not None and res.kind == "CustomResourceDefinition"


def _run_crd_analysis(
    upgrade_resources: list[Resource],
    chart_path: str,
    crd_policy: str,
    release_name: str,
    **kube_opts: str | None,
) -> "CrdReport":
    """Run the CRD analysis pipeline."""
    from helm_preview.crd.pipeline import run_crd_pipeline
    from helm_preview.crd.policy import CrdPolicyMode

    policy_mode = CrdPolicyMode(crd_policy)
    return run_crd_pipeline(
        upgrade_resources=upgrade_resources,
        chart_path=chart_path,
        policy_mode=policy_mode,
        release_name=release_name,
        **kube_opts,
    )


def _fetch_live_objects(
    resources: list[Resource], warnings: list[str], **kube_opts: str | None
) -> list[Resource]:
    """Replace stored release manifests with the live objects from the cluster.

    Resources missing from the cluster are dropped (they will show as ADDED);
    resources that cannot be fetched keep the stored manifest and are reported.
    """
    results: list[Resource] = []
    for res in resources:
        try:
            live_yaml = get_live_object(
                yaml.safe_dump(res.body), res.namespace, **kube_opts
            )
        except RunError as e:
            warnings.append(
                f"Could not fetch live {res.kind}/{res.name}; "
                f"comparing against the stored release manifest ({e.stderr.strip()})"
            )
            results.append(res)
            continue
        if not live_yaml.strip():
            warnings.append(
                f"{res.kind}/{res.name} is in the release but missing from the cluster"
            )
            continue
        live = parse_multi_doc(live_yaml, default_namespace=res.namespace)
        results.append(live[0] if live else res)
    return results


def _apply_server_side(
    resources: list[Resource], warnings: list[str], **kube_opts: str | None
) -> list[Resource]:
    """Apply server-side dry-run to each resource for truth-diff mode."""
    results: list[Resource] = []
    for res in resources:
        try:
            mutated_yaml = server_side_dry_run(
                yaml.safe_dump(res.body), res.namespace, **kube_opts
            )
        except RunError as e:
            warnings.append(
                f"Server-side dry-run failed for {res.kind}/{res.name}; "
                f"showing the client-rendered manifest ({e.stderr.strip()})"
            )
            results.append(res)
            continue
        mutated = parse_multi_doc(mutated_yaml, default_namespace=res.namespace)
        results.append(mutated[0] if mutated else res)
    return results


def _find_resource(
    change: ChangeRecord,
    old_resources: list[Resource],
    new_resources: list[Resource],
) -> Resource | None:
    """Find the Resource object for a change record."""
    # Prefer the current (old) resource: it reflects who manages it today.
    # Keys can differ across an apiVersion migration, so match on identity.
    identity = (change.kind, change.namespace, change.name)
    for res in [*old_resources, *new_resources]:
        if res.key == change.resource_key or (res.kind, res.namespace, res.name) == identity:
            return res
    return None
