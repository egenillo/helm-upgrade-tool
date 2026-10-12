"""Shell out to helm CLI."""

from __future__ import annotations

import re

from helm_preview.core.runner import run


def _kube_flags(**kube_opts: str | None) -> list[str]:
    """Build common kubectl/helm flags from options."""
    flags: list[str] = []
    if kube_opts.get("kubeconfig"):
        flags += ["--kubeconfig", kube_opts["kubeconfig"]]
    if kube_opts.get("kube_context"):
        flags += ["--kube-context", kube_opts["kube_context"]]
    return flags


def get_manifest(release: str, namespace: str, **kube_opts: str | None) -> str:
    """helm get manifest <release> -n <namespace> -> raw YAML string."""
    cmd = ["helm", "get", "manifest", release, "-n", namespace]
    cmd += _kube_flags(**kube_opts)
    return run(cmd)


def dry_run_upgrade(
    release: str,
    chart: str,
    namespace: str,
    values_files: list[str] | None = None,
    set_values: list[str] | None = None,
    version: str | None = None,
    reuse_values: bool = False,
    reset_then_reuse_values: bool = False,
    **kube_opts: str | None,
) -> str:
    """helm upgrade <release> <chart> --dry-run -n <ns> ... -> raw YAML string.

    reuse_values / reset_then_reuse_values are passed straight to helm; they
    control which of the release's previous values the rendered upgrade keeps.

    Strips NOTES: and HOOKS: sections from output.
    """
    cmd = ["helm", "upgrade", release, chart, "--dry-run", "-n", namespace]
    for vf in values_files or []:
        cmd += ["-f", vf]
    for sv in set_values or []:
        cmd += ["--set", sv]
    if version:
        cmd += ["--version", version]
    if reuse_values:
        cmd.append("--reuse-values")
    if reset_then_reuse_values:
        cmd.append("--reset-then-reuse-values")
    cmd += _kube_flags(**kube_opts)

    output = run(cmd)
    return _strip_non_manifest(output)


def _strip_non_manifest(output: str) -> str:
    """Strip NOTES:, HOOKS:, and other non-manifest sections from helm output.

    Helm dry-run output contains sections like:
      HOOKS:
      ---
      ...
      MANIFEST:
      ---
      ...
      NOTES:
      ...

    We want only the content after MANIFEST: and before NOTES:.
    """
    # Try to find MANIFEST: section
    manifest_match = re.search(r"^MANIFEST:\s*\n", output, re.MULTILINE)
    if manifest_match:
        output = output[manifest_match.end():]

    # Strip NOTES: section and everything after it
    notes_match = re.search(r"^NOTES:\s*\n", output, re.MULTILINE)
    if notes_match:
        output = output[:notes_match.start()]

    return output.strip() + "\n"
