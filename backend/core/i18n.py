"""Choice-label translation (Phase 11 of docs/todo.md).

Raw enum *values* stay exactly as they are in API responses -- "SUCCESSFUL",
"SHIPPED" -- code branches on them and tests assert them. The human-readable
translation rides alongside in a ``*_label`` field, resolved through
``gettext`` **at serialization time**, which happens inside the request, so
``Accept-Language`` decides the language (same rule as the error envelope,
``core/exceptions.py``).

The English label is the msgid -- it comes from the model's ``choices``,
which is also what Django admin shows, so a new choice and its translation
can only drift in one place.
"""

from django.utils.translation import gettext as _


def choice_label(choices, value) -> str:
    """The translated label for a choice value; the raw value as last resort."""
    label = dict(choices).get(value, value)
    return str(_(label))
