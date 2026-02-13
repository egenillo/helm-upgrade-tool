"""Detect new CRDs that exist in proposed but not in installed set."""

from __future__ import annotations

from helm_preview.crd.report import NewCrdInfo
from helm_preview.parser.manifest import Resource


def detect_new_crds(
    installed: list[Resource], proposed: list[Resource]
) -> list[NewCrdInfo]:
    """Find CRDs present in proposed but absent from installed.

    Matches by metadata.name (e.g. 'mycrs.example.com').
    """
    installed_names = {r.name for r in installed}

    new_crds: list[NewCrdInfo] = []
    for r in proposed:
        if r.name not in installed_names:
            spec = r.body.get("spec", {})
            group = spec.get("group", "")
            names = spec.get("names", {})
            kind = names.get("kind", "")
            versions = [
                v.get("name", "") for v in spec.get("versions", [])
            ]
            new_crds.append(NewCrdInfo(
                name=r.name,
                group=group,
                kind=kind,
                versions=versions,
            ))

    return new_crds
