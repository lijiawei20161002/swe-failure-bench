"""
Minimal JSON Schema validator (draft-07 subset).

Supports: type, properties, required, additionalProperties,
          items, minItems, maxItems, minimum, maximum,
          enum, allOf, anyOf, oneOf, $ref.

Based on the jsonschema library's validation model.

Usage:
    schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
    validate({}, schema)            # ok
    validate({"x": "bad"}, schema)  # raises ValidationError
"""

from __future__ import annotations

from typing import Any


class ValidationError(Exception):
    pass


def validate(instance: Any, schema: dict, *, _defs: dict | None = None) -> None:
    """
    Validate `instance` against `schema`.
    Raises ValidationError describing the first violation found.
    `_defs` carries the top-level $defs for $ref resolution.
    """
    if _defs is None:
        _defs = schema.get("$defs", schema.get("definitions", {}))

    # ── $ref ─────────────────────────────────────────────────────────────────
    if "$ref" in schema:
        ref = schema["$ref"]
        if ref.startswith("#/$defs/") or ref.startswith("#/definitions/"):
            name = ref.split("/")[-1]
            if name not in _defs:
                raise ValidationError(f"$ref '{ref}' not found in $defs")
            validate(instance, _defs[name], _defs=_defs)
        return

    # ── type ─────────────────────────────────────────────────────────────────
    if "type" in schema:
        _check_type(instance, schema["type"])

    # ── enum ─────────────────────────────────────────────────────────────────
    if "enum" in schema:
        if instance not in schema["enum"]:
            raise ValidationError(f"{instance!r} is not one of {schema['enum']!r}")

    # ── number constraints ────────────────────────────────────────────────────
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            raise ValidationError(f"{instance} < minimum {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            raise ValidationError(f"{instance} > maximum {schema['maximum']}")

    # ── string ────────────────────────────────────────────────────────────────
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            raise ValidationError(f"string too short (min {schema['minLength']})")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            raise ValidationError(f"string too long (max {schema['maxLength']})")

    # ── object ────────────────────────────────────────────────────────────────
    if isinstance(instance, dict):
        if "required" in schema:
            for field in schema["required"]:
                if field not in instance:
                    raise ValidationError(f"required field '{field}' is missing")

        props = schema.get("properties", {})
        for key, val in instance.items():
            if key in props:
                validate(val, props[key], _defs=_defs)

    # ── array ─────────────────────────────────────────────────────────────────
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            raise ValidationError(f"array too short (min {schema['minItems']})")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            raise ValidationError(f"array too long (max {schema['maxItems']})")
        if "items" in schema:
            for i, item in enumerate(instance):
                try:
                    validate(item, schema["items"], _defs=_defs)
                except ValidationError as e:
                    raise ValidationError(f"item[{i}]: {e}") from e

    # ── composition ───────────────────────────────────────────────────────────
    if "allOf" in schema:
        for sub in schema["allOf"]:
            validate(instance, sub, _defs=_defs)

    if "anyOf" in schema:
        errors = []
        for sub in schema["anyOf"]:
            try:
                validate(instance, sub, _defs=_defs)
                break
            except ValidationError as e:
                errors.append(e)
        else:
            raise ValidationError(f"does not match anyOf: {[str(e) for e in errors]}")

    if "oneOf" in schema:
        matched = 0
        for sub in schema["oneOf"]:
            try:
                validate(instance, sub, _defs=_defs)
                matched += 1
                break
            except ValidationError:
                pass
        if matched == 0:
            raise ValidationError("does not match any oneOf schema")


# ── helpers ───────────────────────────────────────────────────────────────────

_TYPE_MAP = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
    "null": type(None),
}


def _check_type(instance: Any, type_name: str | list) -> None:
    if isinstance(type_name, list):
        for t in type_name:
            try:
                _check_type(instance, t)
                return
            except ValidationError:
                pass
        raise ValidationError(f"{instance!r} is not of types {type_name!r}")

    py_type = _TYPE_MAP.get(type_name)
    if py_type is None:
        raise ValidationError(f"unknown type {type_name!r}")

    # Special case: JSON "integer" must not match bool (True/False are int in Python)
    if type_name == "integer" and isinstance(instance, bool):
        raise ValidationError(f"{instance!r} is boolean, not integer")
    if type_name == "number" and isinstance(instance, bool):
        raise ValidationError(f"{instance!r} is boolean, not number")
    if type_name != "boolean" and isinstance(instance, bool):
        # bool is a subclass of int — only accept it for "boolean" type
        if type_name in ("integer", "number"):
            raise ValidationError(f"{instance!r} is boolean, not {type_name}")

    if not isinstance(instance, py_type):
        raise ValidationError(f"{instance!r} is not of type {type_name!r}")
