"""Validation of a product's dynamic attribute values (Phase 12).

One rule set, two callers: the product create/update serializer and (later)
the listing wizard. Keeping it out of the serializer means the admin, the
API and any future import path cannot drift apart.

The rules are deliberately *strict*: unknown keys are rejected instead of
silently dropped (a typo'd filter key that stores quietly is a support
ticket forever), inactive definitions are ignored entirely (turning a field
off must not brick every product that already carries it), and booleans are
``True``/``False`` only — ``"true"`` strings are a client bug we want to
see, not something to guess about.
"""

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError

from .models import AttributeDefinition

MAX_TEXT_LENGTH = 255
YEAR_MIN, YEAR_MAX = 1900, 2100


def _is_empty(value):
    """Empty means "the seller left it out", not "falsy" — ``0`` and
    ``False`` are real answers."""
    return value is None or value == "" or value == [] or value == {}


def _coerce_number(value, key, errors):
    if isinstance(value, bool):
        errors[key] = "Must be a number."
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            number = Decimal(value.strip())
        except InvalidOperation:
            errors[key] = "Must be a number."
            return None
        return int(number) if number == number.to_integral_value() else float(number)
    errors[key] = "Must be a number."
    return None


def _validate_value(definition, value, errors):
    """Coerce and check one value; register a message in ``errors`` on
    failure and return the value to store (or ``None`` to store nothing)."""
    key = definition.key

    if definition.type == AttributeDefinition.Type.TEXT:
        if not isinstance(value, str):
            errors[key] = "Must be text."
            return None
        value = value.strip()
        if not value:
            return None
        if len(value) > MAX_TEXT_LENGTH:
            errors[key] = f"Must be at most {MAX_TEXT_LENGTH} characters."
            return None
        return value

    if definition.type in (AttributeDefinition.Type.NUMBER, AttributeDefinition.Type.YEAR):
        number = _coerce_number(value, key, errors)
        if number is None:
            return None
        if definition.type == AttributeDefinition.Type.YEAR:
            if not float(number).is_integer() or not (YEAR_MIN <= number <= YEAR_MAX):
                errors[key] = f"Must be a year between {YEAR_MIN} and {YEAR_MAX}."
                return None
            return int(number)
        return number

    if definition.type == AttributeDefinition.Type.BOOLEAN:
        if not isinstance(value, bool):
            errors[key] = "Must be true or false."
            return None
        return value

    if definition.type == AttributeDefinition.Type.ENUM:
        allowed = {choice["value"] for choice in definition.choices}
        if not isinstance(value, str) or value not in allowed:
            errors[key] = f"Must be one of: {', '.join(sorted(allowed))}."
            return None
        return value

    if definition.type == AttributeDefinition.Type.RANGE:
        if not isinstance(value, dict) or set(value) != {"min", "max"}:
            errors[key] = "Must be a {min, max} pair."
            return None
        low = _coerce_number(value["min"], key, errors)
        high = _coerce_number(value["max"], key, errors)
        if low is None or high is None:
            return None
        if low > high:
            errors[key] = "The minimum cannot exceed the maximum."
            return None
        return {"min": low, "max": high}

    errors[key] = f"Unknown attribute type {definition.type!r}."  # pragma: no cover
    return None


def validate_attributes(category, attributes, *, enforce_required: bool = True):
    """Return the attributes dict to store, or raise ``ValidationError``.

    ``category`` is the category the product is being filed under — the
    effective definitions (own + ancestors', deeper winning) decide which
    keys exist, which are required and how each value is typed. Without a
    category, no dynamic attributes can be validated, so any non-empty dict
    is rejected.

    ``enforce_required=False`` (Phase 13 drafts) still rejects unknown keys
    and mistyped values — the *shape* must be right the moment it is typed,
    or the typo hides until publish — but lets required keys be absent: a
    half-filled wizard autosave is a save, not a submission. The publish gate
    calls this again with the flag on, which is where "required" becomes
    absolute.
    """
    if attributes is None:
        attributes = {}
    if not isinstance(attributes, dict):
        # Structural problems raise bare messages; the caller (the product
        # serializer) nests them under the ``attributes_json`` field.
        raise ValidationError("Attributes must be an object.")

    if category is None:
        if attributes:
            raise ValidationError("Attributes require a category to validate against.")
        return {}

    definitions = {
        definition.key: definition for definition in category.effective_attribute_definitions()
    }

    errors = {}
    for key in attributes:
        if key not in definitions:
            errors[key] = f"Unknown attribute for '{category.slug}'."

    cleaned = {}
    for key, value in attributes.items():
        definition = definitions.get(key)
        if definition is None:
            continue  # already reported above
        if _is_empty(value):
            continue  # optional field left blank stores nothing
        stored = _validate_value(definition, value, errors)
        if stored is not None:
            cleaned[key] = stored

    if enforce_required:
        for definition in definitions.values():
            if definition.required and definition.key not in cleaned:
                errors.setdefault(definition.key, "This attribute is required.")

    if errors:
        # ``{attribute key: message}`` — the caller nests it under the
        # ``attributes_json`` field so the dynamic form can highlight the
        # offending inputs by key.
        raise ValidationError(errors)
    return cleaned
