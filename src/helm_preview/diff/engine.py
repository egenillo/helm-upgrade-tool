"""Structural YAML diff engine."""

from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass, field
from typing import Any, Literal

from helm_preview.diff.filters import normalize_body, strip_noise
from helm_preview.diff.semantic import _deep_semantic_equal, is_semantically_equal
from helm_preview.parser.manifest import ResourcePair


@dataclass
class FieldChange:
    path: str
    old_value: Any
    new_value: Any
    change_type: str  # "value_changed", "item_added", "item_removed", "type_changed"


@dataclass
class ChangeRecord:
    resource_key: str
    kind: str
    name: str
    namespace: str
    status: Literal["added", "removed", "changed"]
    changes: list[FieldChange] = field(default_factory=list)
    # Removed from the chart, but helm.sh/resource-policy: keep leaves it in the cluster
    kept_on_removal: bool = False


def _keeps_on_removal(res: Any) -> bool:
    annotations = (res.body.get("metadata") or {}).get("annotations") or {}
    return annotations.get("helm.sh/resource-policy") == "keep"


def compute_diff(
    pair: ResourcePair,
    show_all: bool = False,
    extra_ignores: list[str] | None = None,
    secrets: str = "redact",
) -> ChangeRecord | None:
    """Compute diff for a single resource pair.

    `secrets` controls how Secret payload values are shown: "redact"
    (placeholder), "hash" (keyed fingerprint) or "show" (plain text).

    Returns None for unchanged resources.
    """
    if pair.status == "unchanged":
        return None

    if pair.status == "added":
        res = pair.new
        assert res is not None
        return ChangeRecord(
            resource_key=res.key,
            kind=res.kind,
            name=res.name,
            namespace=res.namespace,
            status="added",
        )

    if pair.status == "removed":
        res = pair.old
        assert res is not None
        return ChangeRecord(
            resource_key=res.key,
            kind=res.kind,
            name=res.name,
            namespace=res.namespace,
            status="removed",
            kept_on_removal=_keeps_on_removal(res),
        )

    # status == "changed"
    assert pair.old is not None and pair.new is not None
    old_body = pair.old.body
    new_body = pair.new.body

    if not show_all:
        old_body = strip_noise(old_body, extra_ignores)
        new_body = strip_noise(new_body, extra_ignores)

    old_body = normalize_body(old_body)
    new_body = normalize_body(new_body)

    # Check semantic equality after normalization
    if is_semantically_equal(old_body, new_body):
        return None

    changes = diff_values(old_body, new_body)

    if not changes:
        return None

    if pair.new.kind == "Secret" and secrets != "show":
        changes = [_mask_secret_change(fc, secrets) for fc in changes]

    return ChangeRecord(
        resource_key=pair.new.key,
        kind=pair.new.kind,
        name=pair.new.name,
        namespace=pair.new.namespace,
        status="changed",
        changes=changes,
    )


REDACTED = "<redacted>"

# Secret paths whose values must never be printed. The last-applied annotation
# embeds the full Secret body, so it is just as sensitive as data/stringData.
_SECRET_SENSITIVE_PREFIXES = (
    "data",
    "stringData",
    "metadata.annotations.kubectl\\.kubernetes\\.io/last-applied-configuration",
)


def _mask_secret_change(fc: FieldChange, mode: str) -> FieldChange:
    """Mask Secret payload values (placeholder or fingerprint), keeping the path."""
    if not any(
        fc.path == p or fc.path.startswith(p + ".") or fc.path.startswith(p + "[")
        for p in _SECRET_SENSITIVE_PREFIXES
    ):
        return fc
    return FieldChange(
        path=fc.path,
        old_value=_mask_value(fc.old_value, mode),
        new_value=_mask_value(fc.new_value, mode),
        change_type=fc.change_type,
    )


# Random per process: fingerprints are comparable within one run (old vs new) but
# cannot be precomputed or brute-forced offline, and mean nothing across runs.
_FINGERPRINT_KEY = os.urandom(16)


def fingerprint(value: Any) -> str:
    """Short keyed hash of a value, e.g. '<hash:1a2b3c4d>'."""
    digest = hmac.new(_FINGERPRINT_KEY, str(value).encode(), hashlib.sha256).hexdigest()
    return f"<hash:{digest[:8]}>"


def _mask_value(value: Any, mode: str) -> Any:
    """Mask leaf values, keeping dict keys so users can see what changed."""
    if value is None:
        return None
    if isinstance(value, dict):
        return {k: _mask_value(v, mode) for k, v in value.items()}
    return fingerprint(value) if mode == "hash" else REDACTED


def diff_values(old: Any, new: Any, path: str = "") -> list[FieldChange]:
    """Structural diff of two YAML values into FieldChanges.

    Dict keys are joined with '.', list items are addressed as '[i]'. Lists of
    dicts that all carry a unique string 'name' (containers, env, volumes, CRD
    versions, ...) are matched by name instead of position, so inserting or
    removing one item does not shift the diff of its neighbours. Pure
    reordering of such lists is not reported.
    """
    if isinstance(old, dict) and isinstance(new, dict):
        return _diff_dicts(old, new, path)
    if isinstance(old, list) and isinstance(new, list):
        if _is_keyed_list(old) and _is_keyed_list(new):
            return _diff_keyed_lists(old, new, path)
        return _diff_positional_lists(old, new, path)
    one_is_bool = isinstance(old, bool) != isinstance(new, bool)
    has_str = isinstance(old, str) or isinstance(new, str)
    # Equivalent after coercion (e.g. "80" vs 80), but True is not 1
    if (not one_is_bool or has_str) and _deep_semantic_equal(old, new):
        return []
    change_type = "type_changed" if type(old) is not type(new) else "value_changed"
    return [FieldChange(path=path, old_value=old, new_value=new, change_type=change_type)]


def _join_key(path: str, key: Any) -> str:
    """Append a dict key; dots in keys are escaped so paths work with --ignore-path."""
    key = str(key).replace(".", "\\.")
    return f"{path}.{key}" if path else key


def _diff_dicts(old: dict, new: dict, path: str) -> list[FieldChange]:
    changes: list[FieldChange] = []
    for key, value in old.items():
        if key not in new:
            if value is not None:  # null and missing are equivalent
                changes.append(FieldChange(_join_key(path, key), value, None, "item_removed"))
        else:
            changes.extend(diff_values(value, new[key], _join_key(path, key)))
    for key, value in new.items():
        if key not in old and value is not None:
            changes.append(FieldChange(_join_key(path, key), None, value, "item_added"))
    return changes


def _diff_positional_lists(old: list, new: list, path: str) -> list[FieldChange]:
    changes: list[FieldChange] = []
    for i, (o, n) in enumerate(zip(old, new)):
        changes.extend(diff_values(o, n, f"{path}[{i}]"))
    for i in range(len(new), len(old)):
        changes.append(FieldChange(f"{path}[{i}]", old[i], None, "item_removed"))
    for i in range(len(old), len(new)):
        changes.append(FieldChange(f"{path}[{i}]", None, new[i], "item_added"))
    return changes


def _is_keyed_list(items: list) -> bool:
    """True if items are dicts with unique string 'name' values."""
    if not items or not all(isinstance(i, dict) and isinstance(i.get("name"), str) for i in items):
        return False
    return len({i["name"] for i in items}) == len(items)


def _diff_keyed_lists(old: list, new: list, path: str) -> list[FieldChange]:
    changes: list[FieldChange] = []
    old_by_name = {item["name"]: item for item in old}
    for new_idx, item in enumerate(new):
        item_path = f"{path}[{new_idx}]"
        if item["name"] in old_by_name:
            changes.extend(diff_values(old_by_name[item["name"]], item, item_path))
        else:
            changes.append(FieldChange(item_path, None, item, "item_added"))
    new_names = {item["name"] for item in new}
    for old_idx, item in enumerate(old):
        if item["name"] not in new_names:
            changes.append(FieldChange(f"{path}[{old_idx}]", item, None, "item_removed"))
    return changes


def diff_all(
    pairs: list[ResourcePair],
    show_all: bool = False,
    extra_ignores: list[str] | None = None,
    secrets: str = "redact",
) -> list[ChangeRecord]:
    """Compute diff for all pairs, filter out unchanged."""
    results: list[ChangeRecord] = []
    for pair in pairs:
        record = compute_diff(
            pair, show_all=show_all, extra_ignores=extra_ignores, secrets=secrets
        )
        if record is not None:
            results.append(record)
    return results
