"""CRD ownership conflict detection."""

from __future__ import annotations

from helm_preview.analysis.ownership import OwnershipInfo, detect_ownership
from helm_preview.parser.manifest import Resource


def check_crd_ownership(
    crd: Resource, expected_release: str | None = None
) -> str | None:
    """Check if a CRD is owned by a different Helm release or manager.

    Uses the existing detect_ownership() function to determine who
    manages the CRD, then flags conflicts.

    Returns a conflict description string, or None if no conflict.
    """
    ownership = detect_ownership(crd)

    if ownership.manager == "unknown":
        return None

    if ownership.manager != "helm":
        return (
            f"CRD '{crd.name}' is managed by {ownership.manager}"
            f"{' (app: ' + ownership.app + ')' if ownership.app else ''}, "
            f"not Helm"
        )

    if expected_release and ownership.release and ownership.release != expected_release:
        return (
            f"CRD '{crd.name}' is owned by Helm release '{ownership.release}', "
            f"not the current release '{expected_release}'"
        )

    return None
