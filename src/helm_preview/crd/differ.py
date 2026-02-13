"""CRD-specific pairing and diffing."""

from __future__ import annotations

from helm_preview.diff.engine import FieldChange, _deepdiff_path_to_dot, _extract_changes
from helm_preview.diff.filters import normalize_body, strip_noise
from helm_preview.diff.semantic import is_semantically_equal
from helm_preview.parser.manifest import Resource, ResourcePair

from deepdiff import DeepDiff

# Additional noise paths specific to CRDs (status, timestamps, etc.)
CRD_NOISE_PATHS = [
    "status",
    "metadata.creationTimestamp",
    "metadata.resourceVersion",
    "metadata.uid",
    "metadata.generation",
    "metadata.managedFields",
    "metadata.annotations.meta\\.helm\\.sh/*",
    "metadata.annotations.kubectl\\.kubernetes\\.io/last-applied-configuration",
    "metadata.labels.helm\\.sh/chart",
]


def pair_crds(
    installed: list[Resource], proposed: list[Resource]
) -> list[ResourcePair]:
    """Pair installed vs proposed CRDs by metadata.name.

    Returns ResourcePair list with status: added, removed, changed, unchanged.
    """
    old_map = {r.name: r for r in installed}
    new_map = {r.name: r for r in proposed}

    all_names = list(dict.fromkeys(list(old_map.keys()) + list(new_map.keys())))

    pairs: list[ResourcePair] = []
    for name in all_names:
        old_res = old_map.get(name)
        new_res = new_map.get(name)

        if old_res is None:
            pairs.append(ResourcePair(old=None, new=new_res, status="added"))
        elif new_res is None:
            pairs.append(ResourcePair(old=old_res, new=None, status="removed"))
        elif old_res.body == new_res.body:
            pairs.append(ResourcePair(old=old_res, new=new_res, status="unchanged"))
        else:
            pairs.append(ResourcePair(old=old_res, new=new_res, status="changed"))

    return pairs


def diff_crds(pairs: list[ResourcePair]) -> list[tuple[ResourcePair, list[FieldChange]]]:
    """Diff paired CRDs with CRD-specific noise filtering.

    Returns list of (pair, changes) for pairs that have actual changes.
    """
    results: list[tuple[ResourcePair, list[FieldChange]]] = []

    for pair in pairs:
        if pair.status in ("added", "removed"):
            results.append((pair, []))
            continue

        if pair.status == "unchanged":
            continue

        assert pair.old is not None and pair.new is not None
        old_body = strip_noise(pair.old.body, CRD_NOISE_PATHS)
        new_body = strip_noise(pair.new.body, CRD_NOISE_PATHS)

        old_body = normalize_body(old_body)
        new_body = normalize_body(new_body)

        if is_semantically_equal(old_body, new_body):
            continue

        dd = DeepDiff(old_body, new_body, verbose_level=2)
        changes = _extract_changes(dd)

        if changes:
            results.append((pair, changes))

    return results
