"""Shell out to kubectl CLI."""

from __future__ import annotations

import os

from helm_preview.core.runner import RunError, run


def _kube_flags(**kube_opts: str | None) -> list[str]:
    """Build common kubectl flags from options."""
    flags: list[str] = []
    if kube_opts.get("kubeconfig"):
        flags += ["--kubeconfig", kube_opts["kubeconfig"]]
    if kube_opts.get("kube_context"):
        flags += ["--context", kube_opts["kube_context"]]
    return flags


def current_namespace(**kube_opts: str | None) -> str:
    """Namespace helm would use without -n: HELM_NAMESPACE, else the context's."""
    env_namespace = os.environ.get("HELM_NAMESPACE")
    if env_namespace:
        return env_namespace
    cmd = ["kubectl", "config", "view", "--minify", "-o", "jsonpath={..namespace}"]
    cmd += _kube_flags(**kube_opts)
    try:
        return run(cmd).strip() or "default"
    except RunError:
        return "default"


def server_side_dry_run(
    manifest_yaml: str, namespace: str, **kube_opts: str | None
) -> str:
    """kubectl apply --dry-run=server -o yaml -f - -> post-mutation YAML.

    Feeds single-resource YAML via stdin.
    """
    cmd = [
        "kubectl", "apply",
        "--dry-run=server",
        "-o", "yaml",
        "-n", namespace,
        "-f", "-",
    ]
    cmd += _kube_flags(**kube_opts)
    return run(cmd, stdin=manifest_yaml)


def get_live_object(
    manifest_yaml: str, namespace: str, **kube_opts: str | None
) -> str:
    """kubectl get -f - -o yaml -> the live object identified by the manifest.

    Returns an empty string if the object does not exist in the cluster.
    """
    cmd = [
        "kubectl", "get",
        "--ignore-not-found",
        "-o", "yaml",
        "-n", namespace,
        "-f", "-",
    ]
    cmd += _kube_flags(**kube_opts)
    return run(cmd, stdin=manifest_yaml)
