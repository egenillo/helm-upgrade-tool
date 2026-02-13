"""JSON structured output for CI/CD."""

from __future__ import annotations

import json
from typing import Any

from helm_preview.analysis.ownership import OwnershipInfo
from helm_preview.analysis.risk import RiskAnnotation, RiskLevel
from helm_preview.diff.engine import ChangeRecord


def render_json(
    results: list[tuple[ChangeRecord, list[RiskAnnotation], OwnershipInfo | None]],
    total_unchanged: int = 0,
    crd_report: "CrdReport | None" = None,
) -> str:
    """Produce structured JSON output."""
    added = sum(1 for cr, _, _ in results if cr.status == "added")
    removed = sum(1 for cr, _, _ in results if cr.status == "removed")
    changed = sum(1 for cr, _, _ in results if cr.status == "changed")

    risk_counts = {level.value: 0 for level in RiskLevel}
    for _, annotations, _ in results:
        for a in annotations:
            risk_counts[a.level.value] += 1
    # Changes with no risk annotations count as safe
    for cr, annotations, _ in results:
        if not annotations:
            risk_counts["safe"] += 1

    output: dict[str, Any] = {
        "summary": {
            "added": added,
            "removed": removed,
            "changed": changed,
            "unchanged": total_unchanged,
        },
        "risk_summary": risk_counts,
        "changes": [],
    }

    for change, risk_annotations, ownership in results:
        change_obj: dict[str, Any] = {
            "resource": change.resource_key,
            "kind": change.kind,
            "name": change.name,
            "namespace": change.namespace,
            "status": change.status,
            "risk": [
                {
                    "level": a.level.value,
                    "rule": a.rule,
                    "message": a.message,
                    "path": a.path,
                }
                for a in risk_annotations
            ],
        }

        if ownership:
            change_obj["ownership"] = {
                "manager": ownership.manager,
                "release": ownership.release,
                "app": ownership.app,
            }

        if change.status == "changed":
            change_obj["fields"] = [
                {
                    "path": fc.path,
                    "old": _serialize_value(fc.old_value),
                    "new": _serialize_value(fc.new_value),
                    "type": fc.change_type,
                }
                for fc in change.changes
            ]

        output["changes"].append(change_obj)

    # Add CRD analysis if present
    if crd_report:
        output["crd_analysis"] = crd_report.to_dict()

    return json.dumps(output, indent=2, default=str)


def _serialize_value(value: Any) -> Any:
    """Ensure value is JSON-serializable."""
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    if isinstance(value, (list, tuple)):
        return [_serialize_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    return str(value)
