"""Server-authoritative validation of form answers against a (snapshotted) field schema.

A small fixed interpreter — NO scripting, NO eval, no third-party rule language. Conditional
visibility (`show_if`) and conditional-required (`required_if`) are declarative data evaluated
here. A hidden field's answer is dropped and its `required_if` does not fire. The browser may
mirror these for UX, but this is the only authority.
"""

from __future__ import annotations

import re

FIELD_TYPES = {"text", "number", "date", "select", "multiselect", "boolean", "file"}


class ValidationError(Exception):
    def __init__(self, errors: dict[str, str]):
        self.errors = errors
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))


def _cond_met(cond: dict | None, answers: dict) -> bool:
    """Evaluate a {field, eq} condition against current answers."""
    if not cond:
        return True
    return answers.get(cond.get("field")) == cond.get("eq")


def _check_type(field: dict, value: object) -> str | None:
    t = field.get("type")
    if t == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return "must be a number"
    elif t == "boolean":
        if not isinstance(value, bool):
            return "must be true or false"
    elif t == "multiselect":
        if not isinstance(value, list):
            return "must be a list"
        opts = set(field.get("options") or [])
        if any(v not in opts for v in value):
            return "contains a value that is not an allowed option"
    elif t == "select":
        if value not in (field.get("options") or []):
            return "is not one of the allowed options"
    else:  # text, date, file → string-ish
        if not isinstance(value, str):
            return "must be text"
    return None


def validate(schema: dict, answers: dict) -> dict:
    """Validate `answers` against `schema['fields']`. Returns the CLEANED answers (hidden and
    unknown fields dropped). Raises ValidationError with per-field messages."""
    fields = {f["key"]: f for f in schema.get("fields", []) if isinstance(f, dict)}
    errors: dict[str, str] = {}
    cleaned: dict = {}

    for key, field in fields.items():
        # Conditional visibility: a hidden field contributes nothing and can't be required.
        if not _cond_met(field.get("show_if"), answers):
            continue
        rules = field.get("validation") or {}
        present = key in answers and answers[key] not in (None, "", [])
        required = bool(rules.get("required")) or _cond_met(rules.get("required_if"), answers) \
            and rules.get("required_if") is not None

        if not present:
            if required:
                errors[key] = "is required"
            continue

        value = answers[key]
        type_err = _check_type(field, value)
        if type_err:
            errors[key] = type_err
            continue
        if isinstance(value, str) and rules.get("regex"):
            if not re.fullmatch(rules["regex"], value):
                errors[key] = "is not in the expected format"
                continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if rules.get("min") is not None and value < rules["min"]:
                errors[key] = f"must be at least {rules['min']}"
                continue
            if rules.get("max") is not None and value > rules["max"]:
                errors[key] = f"must be at most {rules['max']}"
                continue
        cleaned[key] = value

    if errors:
        raise ValidationError(errors)
    return cleaned


def validate_schema(schema: dict) -> None:
    """Reject a malformed field schema at form-publish time (fail fast, not at submit)."""
    fields = schema.get("fields")
    if not isinstance(fields, list) or not fields:
        raise ValidationError({"schema": "must have a non-empty 'fields' list"})
    seen = set()
    for f in fields:
        if not isinstance(f, dict) or "key" not in f:
            raise ValidationError({"schema": "each field needs a 'key'"})
        if f["key"] in seen:
            raise ValidationError({"schema": f"duplicate field key: {f['key']}"})
        seen.add(f["key"])
        if f.get("type") not in FIELD_TYPES:
            raise ValidationError({f["key"]: f"unknown field type: {f.get('type')}"})
