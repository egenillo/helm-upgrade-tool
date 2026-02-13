"""Extract CRDs from resources and chart directories."""

from __future__ import annotations

from pathlib import Path

import yaml

from helm_preview.parser.manifest import Resource, parse_multi_doc


def extract_crds_from_resources(resources: list[Resource]) -> list[Resource]:
    """Filter resources to only CRDs."""
    return [r for r in resources if r.kind == "CustomResourceDefinition"]


def extract_crds_from_chart_dir(chart_path: str) -> list[Resource]:
    """Read CRD YAML files from a chart's crds/ directory.

    Helm charts may place CRDs in a top-level crds/ directory.
    Returns parsed Resource objects for each CRD found.
    """
    crds_dir = Path(chart_path) / "crds"
    if not crds_dir.is_dir():
        return []

    resources: list[Resource] = []
    for yaml_file in sorted(crds_dir.glob("*.yaml")):
        try:
            text = yaml_file.read_text(encoding="utf-8")
            parsed = parse_multi_doc(text)
            for r in parsed:
                if r.kind == "CustomResourceDefinition":
                    resources.append(r)
        except (OSError, yaml.YAMLError):
            continue

    # Also check .yml files
    for yaml_file in sorted(crds_dir.glob("*.yml")):
        try:
            text = yaml_file.read_text(encoding="utf-8")
            parsed = parse_multi_doc(text)
            for r in parsed:
                if r.kind == "CustomResourceDefinition":
                    resources.append(r)
        except (OSError, yaml.YAMLError):
            continue

    return resources
