"""Validate CRs against proposed CRD OpenAPI v3 schemas (no jsonschema dep)."""

from __future__ import annotations

from typing import Any


def validate_crs_against_schema(
    crs: list[dict], schema: dict
) -> list[str]:
    """Validate a list of CR bodies against an OpenAPIV3Schema.

    Uses a recursive walker (no external jsonschema dependency).
    Returns list of human-readable validation error strings.
    """
    errors: list[str] = []
    for cr in crs:
        name = cr.get("metadata", {}).get("name", "<unknown>")
        namespace = cr.get("metadata", {}).get("namespace", "")
        prefix = f"{namespace}/{name}" if namespace else name
        cr_errors = _validate_object(cr, schema, "")
        for err in cr_errors:
            errors.append(f"{prefix}: {err}")
    return errors


def _validate_object(value: Any, schema: dict, path: str) -> list[str]:
    """Recursively validate a value against an OpenAPI v3 schema node."""
    errors: list[str] = []

    if not isinstance(schema, dict):
        return errors

    schema_type = schema.get("type")

    # Type checking
    if schema_type and not _check_type(value, schema_type):
        errors.append(f"At '{path}': expected type '{schema_type}', got '{type(value).__name__}'")
        return errors  # Don't recurse if type is wrong

    # Enum validation
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"At '{path}': value {value!r} not in enum {schema['enum']}")

    # Pattern validation
    if "pattern" in schema and isinstance(value, str):
        import re
        try:
            if not re.match(schema["pattern"], value):
                errors.append(f"At '{path}': value '{value}' does not match pattern '{schema['pattern']}'")
        except re.error:
            pass

    # Minimum/maximum
    if "minimum" in schema and isinstance(value, (int, float)):
        if value < schema["minimum"]:
            errors.append(f"At '{path}': value {value} < minimum {schema['minimum']}")
    if "maximum" in schema and isinstance(value, (int, float)):
        if value > schema["maximum"]:
            errors.append(f"At '{path}': value {value} > maximum {schema['maximum']}")

    # Object properties
    if schema_type == "object" and isinstance(value, dict):
        properties = schema.get("properties", {})

        # Check required fields
        required = schema.get("required", [])
        for req in required:
            if req not in value:
                errors.append(f"At '{path}': missing required field '{req}'")

        # Validate known properties
        for prop_name, prop_schema in properties.items():
            if prop_name in value:
                child_path = f"{path}.{prop_name}" if path else prop_name
                errors.extend(_validate_object(value[prop_name], prop_schema, child_path))

        # Check for unknown fields (if no additionalProperties)
        additional = schema.get("additionalProperties")
        if additional is False:
            for key in value:
                if key not in properties and key not in ("apiVersion", "kind", "metadata", "status"):
                    errors.append(f"At '{path}': unknown field '{key}'")
        elif isinstance(additional, dict):
            for key in value:
                if key not in properties:
                    child_path = f"{path}.{key}" if path else key
                    errors.extend(_validate_object(value[key], additional, child_path))

    # Array items
    if schema_type == "array" and isinstance(value, list):
        items_schema = schema.get("items", {})
        for i, item in enumerate(value):
            child_path = f"{path}[{i}]"
            errors.extend(_validate_object(item, items_schema, child_path))

    return errors


def _check_type(value: Any, schema_type: str) -> bool:
    """Check if a value matches the OpenAPI type."""
    if value is None:
        return True  # null is generally acceptable (x-nullable)
    type_map = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "object": dict,
        "array": list,
    }
    expected = type_map.get(schema_type)
    if expected is None:
        return True  # Unknown type, don't reject
    if schema_type == "integer" and isinstance(value, bool):
        return False  # bool is subclass of int in Python
    return isinstance(value, expected)


def find_schema_for_version(crd_body: dict, version: str) -> dict | None:
    """Extract the openAPIV3Schema for a specific version from a CRD body."""
    versions = crd_body.get("spec", {}).get("versions", [])
    for v in versions:
        if v.get("name") == version:
            return v.get("schema", {}).get("openAPIV3Schema")
    return None
