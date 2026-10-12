"""Discover installed CRDs from the cluster via kubectl."""

from __future__ import annotations

import yaml

from helm_preview.core.kubectl import _kube_flags
from helm_preview.core.runner import RunError, run
from helm_preview.parser.manifest import Resource, parse_multi_doc


def discover_cluster_crds(
    names: list[str] | None = None, **kube_opts: str | None
) -> list[Resource] | None:
    """Fetch CRDs from the cluster using kubectl (only `names` if given).

    Returns parsed CRD Resources, or None if the lookup failed (permission
    error, unreachable cluster, unparsable output). An empty list means the
    cluster really has no CRDs.
    """
    if names:
        cmd = ["kubectl", "get", "crd", *names, "--ignore-not-found", "-o", "yaml"]
    else:
        cmd = ["kubectl", "get", "crds", "-o", "yaml"]
    cmd += _kube_flags(**kube_opts)

    try:
        output = run(cmd)
    except RunError:
        return None

    if not output.strip():
        return []  # --ignore-not-found: none of the requested CRDs exist

    # kubectl get -o yaml returns a List wrapper
    try:
        data = yaml.safe_load(output)
    except yaml.YAMLError:
        return None

    if not isinstance(data, dict):
        return None

    # Handle List kind wrapper
    kind = data.get("kind")
    if kind in ("CustomResourceDefinitionList", "List", "CustomResourceDefinition"):
        # A single named CRD comes back bare; several come back as a List
        items = [data] if kind == "CustomResourceDefinition" else data.get("items", [])
        resources: list[Resource] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            metadata = item.get("metadata", {})
            resources.append(Resource(
                api_version=item.get("apiVersion", "apiextensions.k8s.io/v1"),
                kind="CustomResourceDefinition",
                namespace=metadata.get("namespace", ""),
                name=metadata.get("name", ""),
                body=item,
                raw=yaml.dump(item),
            ))
        return resources

    # Fallback: try parsing as multi-doc YAML
    return [
        r for r in parse_multi_doc(output)
        if r.kind == "CustomResourceDefinition"
    ]


def fetch_custom_resources(
    plural: str, group: str, version: str | None = None, **kube_opts: str | None
) -> list[dict]:
    """Fetch all instances of a CR from the cluster.

    Uses: kubectl get <plural>[.<version>].<group> -A -o yaml
    Pinning the version makes the API server return objects in that version,
    so they can be validated against that version's schema.
    Returns list of CR body dicts. On error returns empty list.
    """
    resource_name = f"{plural}.{version}.{group}" if version else f"{plural}.{group}"
    cmd = ["kubectl", "get", resource_name, "-A", "-o", "yaml"]
    cmd += _kube_flags(**kube_opts)

    try:
        output = run(cmd)
    except RunError:
        return []

    try:
        data = yaml.safe_load(output)
    except yaml.YAMLError:
        return []

    if not isinstance(data, dict):
        return []

    return data.get("items", [])
