"""Discover installed CRDs from the cluster via kubectl."""

from __future__ import annotations

import yaml

from helm_preview.core.kubectl import _kube_flags
from helm_preview.core.runner import RunError, run
from helm_preview.parser.manifest import Resource, parse_multi_doc


def discover_cluster_crds(**kube_opts: str | None) -> list[Resource]:
    """Fetch all CRDs from the cluster using kubectl.

    Returns parsed CRD Resources. On permission errors or connection
    failures, logs a warning and returns an empty list.
    """
    cmd = ["kubectl", "get", "crds", "-o", "yaml"]
    cmd += _kube_flags(**kube_opts)

    try:
        output = run(cmd)
    except RunError:
        return []

    # kubectl get -o yaml returns a List wrapper
    try:
        data = yaml.safe_load(output)
    except yaml.YAMLError:
        return []

    if not isinstance(data, dict):
        return []

    # Handle List kind wrapper
    if data.get("kind") == "CustomResourceDefinitionList":
        items = data.get("items", [])
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
    plural: str, group: str, **kube_opts: str | None
) -> list[dict]:
    """Fetch all instances of a CR from the cluster.

    Uses: kubectl get <plural>.<group> -A -o yaml
    Returns list of CR body dicts. On error returns empty list.
    """
    resource_name = f"{plural}.{group}"
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
