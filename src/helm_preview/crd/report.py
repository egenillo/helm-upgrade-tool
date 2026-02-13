"""Data classes for CRD analysis results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from helm_preview.analysis.risk import RiskAnnotation, RiskLevel
from helm_preview.diff.engine import FieldChange


@dataclass
class CrdChangeDetail:
    """A single CRD that was compared (paired old vs new)."""

    name: str
    status: str  # "added", "removed", "changed", "unchanged"
    changes: list[FieldChange] = field(default_factory=list)
    risk_annotations: list[RiskAnnotation] = field(default_factory=list)
    stored_version_warnings: list[str] = field(default_factory=list)
    schema_validation_errors: list[str] = field(default_factory=list)
    ownership_conflict: str | None = None

    @property
    def max_risk(self) -> RiskLevel:
        if not self.risk_annotations:
            return RiskLevel.SAFE
        order = {RiskLevel.SAFE: 0, RiskLevel.WARNING: 1, RiskLevel.DANGER: 2}
        return max(self.risk_annotations, key=lambda a: order[a.level]).level


@dataclass
class NewCrdInfo:
    """A CRD present in the proposed set but not installed."""

    name: str
    group: str
    kind: str
    versions: list[str]


@dataclass
class PolicyResult:
    """Result of policy evaluation."""

    mode: str  # "ignore", "warn", "fail"
    blocked: bool  # True if exit_code should be non-zero
    message: str
    exit_code: int = 0


@dataclass
class CrdReport:
    """Top-level container for all CRD analysis results."""

    crds: list[CrdChangeDetail] = field(default_factory=list)
    new_crds: list[NewCrdInfo] = field(default_factory=list)
    policy_result: PolicyResult | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        """True if any CRD has WARNING or DANGER annotations."""
        for crd in self.crds:
            if crd.max_risk in (RiskLevel.WARNING, RiskLevel.DANGER):
                return True
        return False

    @property
    def has_dangers(self) -> bool:
        """True if any CRD has DANGER annotations."""
        return any(crd.max_risk == RiskLevel.DANGER for crd in self.crds)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output."""
        result: dict[str, Any] = {
            "crds": [],
            "new_crds": [],
            "warnings": self.warnings,
        }

        for crd in self.crds:
            crd_dict: dict[str, Any] = {
                "name": crd.name,
                "status": crd.status,
                "max_risk": crd.max_risk.value,
                "risk_annotations": [
                    {
                        "level": a.level.value,
                        "rule": a.rule,
                        "message": a.message,
                        "path": a.path,
                    }
                    for a in crd.risk_annotations
                ],
                "changes": [
                    {
                        "path": fc.path,
                        "old": fc.old_value,
                        "new": fc.new_value,
                        "type": fc.change_type,
                    }
                    for fc in crd.changes
                ],
            }
            if crd.stored_version_warnings:
                crd_dict["stored_version_warnings"] = crd.stored_version_warnings
            if crd.schema_validation_errors:
                crd_dict["schema_validation_errors"] = crd.schema_validation_errors
            if crd.ownership_conflict:
                crd_dict["ownership_conflict"] = crd.ownership_conflict
            result["crds"].append(crd_dict)

        for new_crd in self.new_crds:
            result["new_crds"].append({
                "name": new_crd.name,
                "group": new_crd.group,
                "kind": new_crd.kind,
                "versions": new_crd.versions,
            })

        if self.policy_result:
            result["policy"] = {
                "mode": self.policy_result.mode,
                "blocked": self.policy_result.blocked,
                "message": self.policy_result.message,
            }

        return result
