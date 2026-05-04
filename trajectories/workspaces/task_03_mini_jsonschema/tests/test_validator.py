"""Tests for JSON Schema validator. Run: pytest tests/ -x"""
import pytest
from validator import validate, ValidationError


# ── basic types ───────────────────────────────────────────────────────────────

class TestTypes:
    def test_string(self):
        validate("hello", {"type": "string"})

    def test_integer(self):
        validate(42, {"type": "integer"})

    def test_bool_is_not_integer(self):
        """JSON booleans must not satisfy type: integer."""
        with pytest.raises(ValidationError):
            validate(True, {"type": "integer"})

    def test_bool_is_not_number(self):
        with pytest.raises(ValidationError):
            validate(False, {"type": "number"})

    def test_wrong_type_raises(self):
        with pytest.raises(ValidationError):
            validate("not-an-int", {"type": "integer"})

    def test_union_type(self):
        validate(None, {"type": ["string", "null"]})
        validate("hi", {"type": ["string", "null"]})
        with pytest.raises(ValidationError):
            validate(1, {"type": ["string", "null"]})


# ── object / properties ───────────────────────────────────────────────────────

class TestObject:
    def test_required_missing_raises(self):
        schema = {"type": "object", "required": ["x"]}
        with pytest.raises(ValidationError, match="required"):
            validate({}, schema)

    def test_required_present_ok(self):
        schema = {"type": "object", "required": ["x"], "properties": {"x": {"type": "integer"}}}
        validate({"x": 1}, schema)

    def test_additional_properties_false_rejects_extra(self):
        schema = {
            "type": "object",
            "properties": {"x": {"type": "integer"}},
            "additionalProperties": False,
        }
        with pytest.raises(ValidationError):
            validate({"x": 1, "y": 2}, schema)

    def test_additional_properties_false_allows_declared(self):
        schema = {
            "type": "object",
            "properties": {"x": {"type": "integer"}},
            "additionalProperties": False,
        }
        validate({"x": 1}, schema)

    def test_additional_properties_schema(self):
        """additionalProperties can be a schema that additional props must satisfy."""
        schema = {
            "type": "object",
            "properties": {"x": {"type": "integer"}},
            "additionalProperties": {"type": "string"},
        }
        validate({"x": 1, "extra": "ok"}, schema)
        with pytest.raises(ValidationError):
            validate({"x": 1, "extra": 99}, schema)


# ── $ref ─────────────────────────────────────────────────────────────────────

class TestRef:
    def test_basic_ref(self):
        schema = {
            "$defs": {"Pos": {"type": "integer", "minimum": 0}},
            "$ref": "#/$defs/Pos",
        }
        validate(5, schema)
        with pytest.raises(ValidationError):
            validate(-1, schema)

    def test_ref_in_property(self):
        schema = {
            "$defs": {"Name": {"type": "string", "minLength": 1}},
            "type": "object",
            "properties": {
                "name": {"$ref": "#/$defs/Name"}
            },
        }
        validate({"name": "alice"}, schema)
        with pytest.raises(ValidationError):
            validate({"name": ""}, schema)

    def test_nested_ref(self):
        """$defs can reference each other."""
        schema = {
            "$defs": {
                "Str": {"type": "string"},
                "Pair": {
                    "type": "object",
                    "required": ["a", "b"],
                    "properties": {
                        "a": {"$ref": "#/$defs/Str"},
                        "b": {"$ref": "#/$defs/Str"},
                    },
                },
            },
            "$ref": "#/$defs/Pair",
        }
        validate({"a": "x", "b": "y"}, schema)
        with pytest.raises(ValidationError):
            validate({"a": 1, "b": "y"}, schema)

    def test_unknown_ref_raises(self):
        schema = {"$ref": "#/$defs/Missing"}
        with pytest.raises(ValidationError):
            validate({}, schema)


# ── oneOf ─────────────────────────────────────────────────────────────────────

class TestOneOf:
    def test_exactly_one_match_ok(self):
        schema = {
            "oneOf": [
                {"type": "string"},
                {"type": "integer"},
            ]
        }
        validate("hello", schema)
        validate(42, schema)

    def test_zero_matches_raises(self):
        schema = {
            "oneOf": [
                {"type": "string"},
                {"type": "integer"},
            ]
        }
        with pytest.raises(ValidationError):
            validate([], schema)

    def test_two_matches_raises(self):
        """oneOf must fail when the instance satisfies MORE THAN ONE sub-schema."""
        schema = {
            "oneOf": [
                {"type": "number"},   # 42 satisfies this (integer is a number)
                {"type": "integer"},  # 42 satisfies this too
            ]
        }
        with pytest.raises(ValidationError):
            validate(42, schema)

    def test_three_sub_schemas_exactly_one(self):
        schema = {
            "oneOf": [
                {"type": "string", "minLength": 5},
                {"type": "string", "maxLength": 3},
                {"type": "integer"},
            ]
        }
        validate("hi", schema)       # matches maxLength<=3 only
        validate(99, schema)         # matches integer only
        with pytest.raises(ValidationError):
            validate("hello", schema)  # only matches minLength>=5
        # a 4-char string matches neither → 0 matches
        with pytest.raises(ValidationError):
            validate("hell", schema)


# ── allOf / anyOf ─────────────────────────────────────────────────────────────

class TestComposition:
    def test_allof_all_must_pass(self):
        schema = {
            "allOf": [
                {"type": "integer"},
                {"minimum": 0},
                {"maximum": 100},
            ]
        }
        validate(50, schema)
        with pytest.raises(ValidationError):
            validate(150, schema)

    def test_anyof_one_suffices(self):
        schema = {
            "anyOf": [
                {"type": "string"},
                {"type": "integer"},
            ]
        }
        validate("ok", schema)
        validate(1, schema)
        with pytest.raises(ValidationError):
            validate([], schema)

    def test_allof_with_required_in_sub(self):
        """required inside allOf sub-schemas must still be enforced."""
        schema = {
            "type": "object",
            "allOf": [
                {"required": ["x"]},
                {"required": ["y"]},
            ],
        }
        validate({"x": 1, "y": 2}, schema)
        with pytest.raises(ValidationError):
            validate({"x": 1}, schema)   # missing y
