"""Classify CRD changes into graduated risk levels."""

from __future__ import annotations

import re

from helm_preview.analysis.risk import RiskAnnotation, RiskLevel
from helm_preview.diff.engine import FieldChange


def classify_crd_changes(changes: list[FieldChange]) -> list[RiskAnnotation]:
    """Apply graduated risk classification to each CRD field change.

    Returns a RiskAnnotation per change based on path pattern matching.
    """
    annotations: list[RiskAnnotation] = []
    for fc in changes:
        annotation = _classify_single(fc)
        annotations.append(annotation)
    return annotations


def _classify_single(fc: FieldChange) -> RiskAnnotation:
    """Classify a single FieldChange against the CRD path rules."""
    path = fc.path
    change_type = fc.change_type

    # --- SAFE patterns ---

    # Metadata annotations/labels changes
    if re.match(r"^metadata\.(annotations|labels)\.", path):
        return _annotation(RiskLevel.SAFE, "crd_metadata_change",
                           f"Metadata change at '{path}'", path)

    # Additional printer columns (cosmetic)
    if re.search(r"spec\.versions\[\d+\]\.additionalPrinterColumns", path):
        return _annotation(RiskLevel.SAFE, "crd_printer_columns",
                           f"Printer column change at '{path}'", path)

    # New version added (whole entry added to spec.versions)
    if re.match(r"^spec\.versions\[\d+\]$", path) and change_type == "item_added":
        return _annotation(RiskLevel.SAFE, "crd_version_added",
                           "New CRD version added", path)

    # New optional property added deep in schema
    if (re.search(r"spec\.versions\[\d+\]\.schema\.openAPIV3Schema\.properties\.\w+\.properties\.\w+", path)
            and change_type == "item_added"
            and not re.search(r"\.required", path)):
        return _annotation(RiskLevel.SAFE, "crd_optional_property_added",
                           f"New optional property added at '{path}'", path)

    # --- DANGER patterns ---

    # Removed version (whole entry removed from spec.versions)
    if re.match(r"^spec\.versions\[\d+\]$", path) and change_type == "item_removed":
        return _annotation(RiskLevel.DANGER, "crd_version_removed",
                           "CRD version removed", path)

    # New required field added
    if (re.search(r"spec\.versions\[\d+\]\.schema\..*\.required", path)
            and change_type == "item_added"):
        return _annotation(RiskLevel.DANGER, "crd_required_field_added",
                           f"New required field added at '{path}'", path)

    # Property removed from schema
    if (re.search(r"spec\.versions\[\d+\]\.schema\..*\.properties\.\w+$", path)
            and change_type == "item_removed"):
        return _annotation(RiskLevel.DANGER, "crd_property_removed",
                           f"Schema property removed at '{path}'", path)

    # Type changed
    if (re.search(r"spec\.versions\[\d+\]\.schema\..*\.properties\.\w+\.type$", path)
            and change_type == "value_changed"):
        return _annotation(RiskLevel.DANGER, "crd_type_changed",
                           f"Property type changed at '{path}'", path)

    # Scope changed
    if path == "spec.scope" and change_type == "value_changed":
        return _annotation(RiskLevel.DANGER, "crd_scope_changed",
                           f"CRD scope changed from '{fc.old_value}' to '{fc.new_value}'",
                           path)

    # Conversion strategy changed
    if path == "spec.conversion.strategy" and change_type == "value_changed":
        return _annotation(RiskLevel.DANGER, "crd_conversion_strategy_changed",
                           f"Conversion strategy changed from '{fc.old_value}' to '{fc.new_value}'",
                           path)

    # --- WARNING patterns ---

    # Default value changed
    if (re.search(r"spec\.versions\[\d+\]\.schema\..*\.properties\.\w+\.default$", path)
            and change_type == "value_changed"):
        return _annotation(RiskLevel.WARNING, "crd_default_changed",
                           f"Default value changed at '{path}'", path)

    # Pattern changed (tighter validation)
    if (re.search(r"spec\.versions\[\d+\]\.schema\..*\.properties\.\w+\.pattern$", path)
            and change_type == "value_changed"):
        return _annotation(RiskLevel.WARNING, "crd_pattern_changed",
                           f"Validation pattern changed at '{path}'", path)

    # Min/max range changed
    if (re.search(r"spec\.versions\[\d+\]\.schema\..*\.properties\.\w+\.(minimum|maximum)$", path)
            and change_type == "value_changed"):
        return _annotation(RiskLevel.WARNING, "crd_range_changed",
                           f"Validation range changed at '{path}'", path)

    # Enum changed
    if re.search(r"spec\.versions\[\d+\]\.schema\..*\.properties\.\w+\.enum", path):
        return _annotation(RiskLevel.WARNING, "crd_enum_changed",
                           f"Enum values changed at '{path}'", path)

    # Webhook config changed
    if re.search(r"^spec\.conversion\.webhook\.", path):
        return _annotation(RiskLevel.WARNING, "crd_webhook_changed",
                           f"Conversion webhook configuration changed at '{path}'", path)

    # Required field value changed (not added/removed, but list value changed)
    if re.search(r"spec\.versions\[\d+\]\.schema\..*\.required", path):
        if change_type == "item_removed":
            return _annotation(RiskLevel.SAFE, "crd_required_field_removed",
                               f"Required field constraint removed at '{path}'", path)
        if change_type == "value_changed":
            return _annotation(RiskLevel.DANGER, "crd_required_changed",
                               f"Required fields changed at '{path}'", path)

    # Catch-all for any other CRD change
    return _annotation(RiskLevel.WARNING, "crd_unknown_change",
                       f"Unknown CRD change at '{path}'", path)


def _annotation(level: RiskLevel, rule: str, message: str, path: str) -> RiskAnnotation:
    return RiskAnnotation(level=level, rule=rule, message=message, path=path)
