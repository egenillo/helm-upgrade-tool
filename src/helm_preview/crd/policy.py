"""CRD policy evaluation (ignore / warn / fail)."""

from __future__ import annotations

from enum import Enum

from helm_preview.analysis.risk import RiskLevel
from helm_preview.crd.report import CrdChangeDetail, CrdReport, PolicyResult


class CrdPolicyMode(Enum):
    IGNORE = "ignore"
    WARN = "warn"
    FAIL = "fail"


def evaluate_policy(report: CrdReport, mode: CrdPolicyMode) -> PolicyResult:
    """Evaluate CRD changes against the chosen policy mode.

    - ignore: always pass
    - warn: pass but emit warnings for issues
    - fail: block (exit 1) if any DANGER-level CRD changes exist
    """
    if mode == CrdPolicyMode.IGNORE:
        return PolicyResult(
            mode=mode.value,
            blocked=False,
            message="CRD policy: ignore (all CRD issues suppressed)",
            exit_code=0,
        )

    danger_crds = [c for c in report.crds if c.max_risk == RiskLevel.DANGER]
    warning_crds = [c for c in report.crds if c.max_risk == RiskLevel.WARNING]

    if mode == CrdPolicyMode.WARN:
        parts: list[str] = []
        if danger_crds:
            names = ", ".join(c.name for c in danger_crds)
            parts.append(f"{len(danger_crds)} CRD(s) with DANGER-level changes: {names}")
        if warning_crds:
            names = ", ".join(c.name for c in warning_crds)
            parts.append(f"{len(warning_crds)} CRD(s) with WARNING-level changes: {names}")
        if not parts:
            msg = "CRD policy: warn (no issues found)"
        else:
            msg = "CRD policy: warn - " + "; ".join(parts)
        return PolicyResult(
            mode=mode.value,
            blocked=False,
            message=msg,
            exit_code=0,
        )

    # mode == FAIL
    if danger_crds:
        names = ", ".join(c.name for c in danger_crds)
        return PolicyResult(
            mode=mode.value,
            blocked=True,
            message=f"CRD policy: fail - {len(danger_crds)} CRD(s) with DANGER-level changes: {names}",
            exit_code=1,
        )

    if warning_crds:
        names = ", ".join(c.name for c in warning_crds)
        return PolicyResult(
            mode=mode.value,
            blocked=False,
            message=f"CRD policy: fail (passed) - {len(warning_crds)} CRD(s) with WARNING-level changes: {names}",
            exit_code=0,
        )

    return PolicyResult(
        mode=mode.value,
        blocked=False,
        message="CRD policy: fail (passed) - no issues found",
        exit_code=0,
    )
