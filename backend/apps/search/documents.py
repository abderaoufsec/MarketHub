"""The text one listing contributes to the search index (Phase 15).

``Product.search_document`` is a denormalized, normalized string, rebuilt on
every save. It is not the description alone: a buyer searches for a *brand*,
a *wilaya*, a *category*, or a *model year* as often as for a title, and all
of those live in different tables. Putting them in one indexed column is the
cheap, robust half of the "Postgres first" engine decision - the other half is
the trigram index that makes typos survivable.

Design notes:

* Arabic tokens are appended in Latin transliteration as well, so a listing
  titled ``هاتف سامسونج`` is reachable from a Latin keyboard even before the
  synonym table knows the exact word.
* Enum values are stored by value *and* label: the API stores ``used_good``,
  the shopper types "bon état".
* Nothing user-private goes in: no seller phone, no email, no draft-only
  fields. The index is as public as the listing page.
"""

from __future__ import annotations

import json

from .normalization import latin_tokens, normalize_text

#: Attribute keys whose values are pure noise in an index (internal flags,
#: coordinates, free-form JSON the seller pasted). Kept short and explicit.
SKIPPED_ATTRIBUTE_KEYS = frozenset({"latitude", "longitude", "lat", "lng"})


def _category_text(product) -> list[str]:
    category = getattr(product, "category", None)
    if category is None:
        return []
    parts = []
    try:
        chain = category.get_ancestors(include_self=True)
    except (AttributeError, ValueError):
        chain = [category]
    for node in chain:
        parts.extend([node.name_fr, node.name_ar, node.name_en])
    return [part for part in parts if part]


def _location_text(product) -> list[str]:
    parts = []
    wilaya = getattr(product, "wilaya", None)
    if wilaya is not None:
        parts.extend([wilaya.name_fr, wilaya.name_ar, wilaya.name_en])
    commune = getattr(product, "commune", None)
    if commune is not None:
        parts.extend([commune.name_fr, commune.name_ar, commune.name_en])
    return [part for part in parts if part]


def _attribute_text(product) -> list[str]:
    attributes = getattr(product, "attributes_json", None) or {}
    if not isinstance(attributes, dict):
        return []
    parts = []
    definitions = {}
    category = getattr(product, "category", None)
    if category is not None:
        try:
            definitions = {d.key: d for d in category.effective_attribute_definitions()}
        except (AttributeError, ValueError):
            definitions = {}
    for key, value in attributes.items():
        if key in SKIPPED_ATTRIBUTE_KEYS:
            continue
        parts.append(str(key).replace("_", " "))
        if isinstance(value, dict):
            parts.extend(str(item) for item in value.values())
        elif isinstance(value, (list, tuple)):
            parts.extend(str(item) for item in value)
        else:
            parts.append(str(value))
        definition = definitions.get(key)
        if definition is not None and not isinstance(value, (dict, list, tuple)):
            # The human label, not just the machine value ("bon état" vs
            # "used_good"), and the matching choice label.
            parts.append(getattr(definition, "label_fr", "") or "")
            for choice in getattr(definition, "choices", None) or []:
                if str(choice.get("value")) == str(value):
                    parts.extend(
                        filter(
                            None,
                            (
                                choice.get("label_fr"),
                                choice.get("label_ar"),
                                choice.get("label_en"),
                            ),
                        )
                    )
                    break
    return parts


def build_search_document(product) -> str:
    """The normalized index text for ``product``.

    Never raises on a partially built instance (the wizard saves drafts with
    almost every relation unset): each section tolerates ``None``.
    """
    parts = [
        getattr(product, "name", "") or "",
        getattr(product, "description", "") or "",
        getattr(product, "listing_type", "") or "",
        getattr(product, "price_mode", "") or "",
    ]
    store = getattr(product, "store", None)
    if store is not None:
        parts.extend([store.store_name, "boutique store magasin"])

    parts.extend(_category_text(product))
    parts.extend(_location_text(product))
    parts.extend(_attribute_text(product))

    raw = " ".join(part for part in parts if part)
    normalized = normalize_text(raw)
    latin = latin_tokens(raw)
    # The raw normalized text is what queries match; the Latin transliteration
    # widens Arabic listings to a Latin keyboard. Keep the JSON attributes out
    # of the final string but make sure dict/list values were readable.
    if latin:
        return f"{normalized} {latin}".strip()
    return normalized


def document_from_attributes(attributes) -> str:
    """Fallback used by the data migration (no model helpers available)."""
    if not isinstance(attributes, dict):
        return ""
    values = []
    for key, value in attributes.items():
        if key in SKIPPED_ATTRIBUTE_KEYS:
            continue
        values.append(str(key).replace("_", " "))
        if isinstance(value, (dict, list, tuple)):
            values.append(json.dumps(value, ensure_ascii=False))
        else:
            values.append(str(value))
    return normalize_text(" ".join(values))
