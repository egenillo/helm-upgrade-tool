"""Orchestrate CRD analysis pipeline."""

from __future__ import annotations

import click

from helm_preview.crd.classifier import classify_crd_changes
from helm_preview.crd.detect_new import detect_new_crds
from helm_preview.crd.differ import diff_crds, pair_crds
from helm_preview.crd.discovery import discover_cluster_crds, fetch_custom_resources
from helm_preview.crd.extraction import extract_crds_from_chart_dir, extract_crds_from_resources
from helm_preview.crd.ownership import check_crd_ownership
from helm_preview.crd.policy import CrdPolicyMode, evaluate_policy
from helm_preview.crd.report import CrdChangeDetail, CrdReport
from helm_preview.crd.schema_validator import find_schema_for_version, validate_crs_against_schema
from helm_preview.crd.stored_versions import check_stored_version_safety
from helm_preview.parser.manifest import Resource


def run_crd_pipeline(
    upgrade_resources: list[Resource],
    chart_path: str | None = None,
    policy_mode: CrdPolicyMode = CrdPolicyMode.WARN,
    release_name: str | None = None,
    **kube_opts: str | None,
) -> CrdReport:
    """Run full CRD analysis pipeline.

    Steps:
    1. Extract proposed CRDs from upgrade_resources + chart crds/ dir
    2. Discover installed CRDs from cluster (kubectl get crds)
    3. Pair installed vs proposed by metadata.name
    4. Diff paired CRDs (CRD-specific noise filtering)
    5. Classify each change → graduated RiskAnnotations
    6. Detect new CRDs (in proposed but not installed)
    7. Check ownership/conflicts for existing CRDs
    8. Validate live CRs against proposed schema
    9. Check stored-version safety
    10. Evaluate policy
    11. Assemble CrdReport
    """
    report = CrdReport()

    # Step 1: Extract proposed CRDs
    proposed_crds = extract_crds_from_resources(upgrade_resources)
    if chart_path:
        chart_crds = extract_crds_from_chart_dir(chart_path)
        # Merge, preferring resources from upgrade (they may be templated)
        existing_names = {r.name for r in proposed_crds}
        for c in chart_crds:
            if c.name not in existing_names:
                proposed_crds.append(c)

    if not proposed_crds:
        report.policy_result = evaluate_policy(report, policy_mode)
        return report

    # Step 2: Discover installed CRDs
    installed_crds = discover_cluster_crds(**kube_opts)
    if not installed_crds:
        report.warnings.append(
            "Could not retrieve installed CRDs from cluster "
            "(permission denied or cluster unreachable). "
            "Comparing against empty set."
        )

    # Filter installed CRDs to only those relevant (same names as proposed)
    proposed_names = {r.name for r in proposed_crds}
    installed_relevant = [r for r in installed_crds if r.name in proposed_names]

    # Also include installed CRDs that are being removed (not in proposed)
    # Actually, we only analyze CRDs the chart manages, so just use proposed names
    # plus any installed that might be dropped.

    # Step 3: Pair installed vs proposed
    pairs = pair_crds(installed_relevant, proposed_crds)

    # Step 4: Diff paired CRDs
    diff_results = diff_crds(pairs)

    # Step 5-9: Process each pair
    for pair, changes in diff_results:
        crd_name = (pair.new or pair.old).name  # type: ignore[union-attr]
        detail = CrdChangeDetail(
            name=crd_name,
            status=pair.status,
            changes=changes,
        )

        # Step 5: Classify changes
        if changes:
            detail.risk_annotations = classify_crd_changes(changes)

        # Step 7: Check ownership
        old_crd = pair.old
        if old_crd:
            conflict = check_crd_ownership(old_crd, expected_release=release_name)
            if conflict:
                detail.ownership_conflict = conflict

        # Step 8: Schema validation (only for changed CRDs with schemas)
        if pair.new and pair.status == "changed":
            _validate_live_crs(pair.new, detail, report, **kube_opts)

        # Step 9: Stored version safety
        if pair.old and pair.new and pair.status == "changed":
            sv_warnings = check_stored_version_safety(pair.old, pair.new)
            detail.stored_version_warnings = sv_warnings

        report.crds.append(detail)

    # Step 6: Detect new CRDs
    report.new_crds = detect_new_crds(installed_relevant, proposed_crds)

    # Step 10: Evaluate policy
    report.policy_result = evaluate_policy(report, policy_mode)

    return report


def _validate_live_crs(
    new_crd: Resource,
    detail: CrdChangeDetail,
    report: CrdReport,
    **kube_opts: str | None,
) -> None:
    """Fetch live CRs and validate against the proposed schema."""
    spec = new_crd.body.get("spec", {})
    names = spec.get("names", {})
    plural = names.get("plural", "")
    group = spec.get("group", "")

    if not plural or not group:
        return

    crs = fetch_custom_resources(plural, group, **kube_opts)
    if not crs:
        return

    # Find the storage version schema
    versions = spec.get("versions", [])
    storage_version = None
    for v in versions:
        if v.get("storage"):
            storage_version = v.get("name")
            break

    if not storage_version:
        return

    schema = find_schema_for_version(new_crd.body, storage_version)
    if not schema:
        return

    errors = validate_crs_against_schema(crs, schema)
    if errors:
        detail.schema_validation_errors = errors
