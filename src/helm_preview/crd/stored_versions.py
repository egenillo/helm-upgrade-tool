"""Check stored-version safety when CRD versions are removed."""

from __future__ import annotations

from helm_preview.parser.manifest import Resource


def check_stored_version_safety(
    old_crd: Resource, new_crd: Resource
) -> list[str]:
    """Check if removing CRD versions would leave stored versions orphaned.

    Reads status.storedVersions from the old (installed) CRD and checks that
    all stored versions still exist in the new CRD's spec.versions.

    Returns list of warning messages for any unsafe removals.
    """
    old_status = old_crd.body.get("status", {})
    stored_versions = old_status.get("storedVersions", [])

    if not stored_versions:
        return []

    new_spec = new_crd.body.get("spec", {})
    new_version_names = {
        v.get("name", "") for v in new_spec.get("versions", [])
    }

    warnings: list[str] = []
    for sv in stored_versions:
        if sv not in new_version_names:
            warnings.append(
                f"Stored version '{sv}' is still in status.storedVersions "
                f"but is being removed from spec.versions. "
                f"Existing objects stored as '{sv}' may become inaccessible. "
                f"Migrate objects before removing the version."
            )

    return warnings
