"""Multi-doc YAML parsing, resource keying, and pairing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import yaml


@dataclass
class Resource:
    api_version: str
    kind: str
    namespace: str
    name: str
    body: dict
    raw: str

    @property
    def key(self) -> str:
        return f"{self.api_version}/{self.kind}/{self.namespace}/{self.name}"


@dataclass
class ResourcePair:
    old: Resource | None
    new: Resource | None
    status: Literal["added", "removed", "changed", "unchanged"]


def parse_multi_doc(yaml_text: str, default_namespace: str = "default") -> list[Resource]:
    """Split multi-doc YAML (---) into Resource objects.

    Skips empty docs and non-resource docs (those without apiVersion/kind).
    """
    resources: list[Resource] = []
    # Split on --- lines preserving each document's raw text
    raw_docs = _split_raw_docs(yaml_text)

    for raw_doc in raw_docs:
        stripped = raw_doc.strip()
        if not stripped:
            continue

        try:
            body = yaml.safe_load(stripped)
        except yaml.YAMLError:
            continue

        if not isinstance(body, dict):
            continue

        # Skip non-resource docs (must have apiVersion and kind)
        if "apiVersion" not in body or "kind" not in body:
            continue

        metadata = body.get("metadata") or {}
        resources.append(Resource(
            api_version=body["apiVersion"],
            kind=body["kind"],
            namespace=metadata.get("namespace", default_namespace),
            name=metadata.get("name", ""),
            body=body,
            raw=stripped,
        ))

    return resources


def _split_raw_docs(yaml_text: str) -> list[str]:
    """Split multi-doc YAML by --- delimiters, returning raw text per doc."""
    docs: list[str] = []
    current_lines: list[str] = []

    for line in yaml_text.splitlines(keepends=True):
        if line.rstrip() == "---":
            if current_lines:
                docs.append("".join(current_lines))
                current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        docs.append("".join(current_lines))

    return docs


def pair_resources(
    old: list[Resource], new: list[Resource]
) -> list[ResourcePair]:
    """Match resources by key. Returns list of ResourcePair.

    old=None -> ADDED, new=None -> REMOVED, both -> CHANGED/UNCHANGED.

    Resources that only differ in apiVersion (e.g. autoscaling/v2beta2 ->
    autoscaling/v2) are paired as CHANGED rather than REMOVED + ADDED, as long
    as kind/namespace/name identifies a single resource on each side.
    """
    old_map = {r.key: r for r in old}
    new_map = {r.key: r for r in new}

    # Fallback pairing for apiVersion migrations among unmatched resources
    unmatched_old = [r for k, r in old_map.items() if k not in new_map]
    unmatched_new = [r for k, r in new_map.items() if k not in old_map]
    old_by_identity = _unique_by_identity(unmatched_old)
    new_by_identity = _unique_by_identity(unmatched_new)
    migrated: dict[str, Resource] = {}  # new key -> old resource
    for identity, new_res in new_by_identity.items():
        old_res = old_by_identity.get(identity)
        if old_res is not None:
            migrated[new_res.key] = old_res
    migrated_old_keys = {r.key for r in migrated.values()}

    all_keys = list(dict.fromkeys(list(old_map.keys()) + list(new_map.keys())))

    pairs: list[ResourcePair] = []
    for key in all_keys:
        if key in migrated_old_keys:
            continue  # emitted together with its new-apiVersion counterpart
        old_res = old_map.get(key) or migrated.get(key)
        new_res = new_map.get(key)

        if old_res is None:
            status: Literal["added", "removed", "changed", "unchanged"] = "added"
        elif new_res is None:
            status = "removed"
        elif old_res.body == new_res.body:
            status = "unchanged"
        else:
            status = "changed"

        pairs.append(ResourcePair(old=old_res, new=new_res, status=status))

    return pairs


def _unique_by_identity(resources: list[Resource]) -> dict[tuple[str, str, str], Resource]:
    """Index resources by (kind, namespace, name), dropping ambiguous identities."""
    index: dict[tuple[str, str, str], Resource] = {}
    ambiguous: set[tuple[str, str, str]] = set()
    for r in resources:
        identity = (r.kind, r.namespace, r.name)
        if identity in index:
            ambiguous.add(identity)
        index[identity] = r
    for identity in ambiguous:
        del index[identity]
    return index
