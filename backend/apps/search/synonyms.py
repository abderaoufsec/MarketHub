"""Bilingual synonym expansion (Phase 15 of docs/todo.md).

Algerian classifieds are searched in four overlapping vocabularies: Arabic,
French, English, and Darija/Arabizi (Latin spelling of Arabic). A buyer types
``tomobile`` or ``سيارة`` and expects the listing titled ``Voiture Renault``.
Full-text search cannot infer that; a curated thesaurus can.

Every group is one concept. Query expansion turns each token into an OR group
of its group members, and groups are AND-ed - so ``samsung telephone`` still
requires both concepts, while any spelling of each is accepted. The table is
intentionally small and reviewed: adding a word here is a product decision,
not a language-model guess.
"""

from __future__ import annotations

from .normalization import normalize_text, tokenize

#: concept -> spellings. All spellings are normalized at import time.
SYNONYM_GROUPS: dict[str, tuple[str, ...]] = {
    "telephone": (
        "telephone",
        "téléphone",
        "tel",
        "phone",
        "smartphone",
        "mobile",
        "portable",
        "gsm",
        "هاتف",
        "هواتف",
        "تلفون",
        "تيليفون",
        "hatif",
        "hatf",
        "telfoun",
        "telifoun",
    ),
    "car": (
        "voiture",
        "car",
        "auto",
        "automobile",
        "véhicule",
        "vehicule",
        "سيارة",
        "سيارات",
        "sayara",
        "sayarat",
        "tomobile",
        "tonobile",
        "karhba",
    ),
    "motorcycle": (
        "moto",
        "motos",
        "motorcycle",
        "scooter",
        "scooter",
        "دراجة",
        "موتور",
        "moto",
        "motocyclette",
    ),
    "apartment": (
        "appartement",
        "appart",
        "apartment",
        "flat",
        "شقة",
        "شققة",
        "appartement",
        "chka",
        "chqa",
    ),
    "house": (
        "maison",
        "house",
        "villa",
        "dar",
        "دار",
        "منزل",
        "فيلا",
        "villa",
        "houch",
    ),
    "land": (
        "terrain",
        "land",
        "plot",
        "أرض",
        "ارض",
        "قطعة",
        "ard",
        "terrains",
    ),
    "job": (
        "emploi",
        "job",
        "travail",
        "work",
        "recrutement",
        "خدمة",
        "عمل",
        "وظيفة",
        "khedma",
        "khadma",
        "travail",
    ),
    "clothes": (
        "vêtements",
        "vetements",
        "clothes",
        "clothing",
        "ملابس",
        "لباس",
        "حوايج",
        "hwayej",
        "libas",
    ),
    "shoes": (
        "chaussures",
        "chaussure",
        "shoes",
        "sneakers",
        "أحذية",
        "احذية",
        "صباط",
        "sabat",
        "sbabet",
    ),
    "fridge": (
        "réfrigérateur",
        "refrigerateur",
        "frigo",
        "fridge",
        "ثلاجة",
        "ثلاجات",
        "talaja",
        "tallaja",
    ),
    "washing_machine": (
        "lave-linge",
        "lave",
        "linge",
        "washing",
        "machine",
        "غسالة",
        "غسالات",
        "ghassala",
        "ghasala",
    ),
    "phone_brand_samsung": ("samsung", "سامسونج", "samsong", "samsounge"),
    "phone_brand_apple": ("apple", "iphone", "ايفون", "أيفون", "ابل", "apple"),
    "phone_brand_xiaomi": ("xiaomi", "redmi", "شاومي", "xiaomi"),
    "phone_brand_condor": ("condor", "كوندور", "condor"),
    "phone_brand_oppo": ("oppo", "أوبو", "اوبو"),
    "car_brand_renault": ("renault", "رينو", "renault"),
    "car_brand_peugeot": ("peugeot", "بيجو", "peugeot"),
    "car_brand_toyota": ("toyota", "تويوتا", "toyota"),
    "car_brand_hyundai": ("hyundai", "هيونداي", "hyundai"),
    "car_brand_dacia": ("dacia", "داسيا", "dacia"),
    "car_brand_kia": ("kia", "كيا", "kia"),
}

#: Built once: normalized spelling -> every normalized member of its group.
_INDEX: dict[str, set[str]] = {}
for _members in SYNONYM_GROUPS.values():
    _normalized = {normalize_text(member) for member in _members}
    _normalized.discard("")
    for _member in _normalized:
        _INDEX.setdefault(_member, set()).update(_normalized)

#: Every normalized spelling, for suggestions/did-you-mean vocabulary.
VOCABULARY: frozenset[str] = frozenset(_INDEX)


def expand_token(token: str) -> set[str]:
    """All spellings that should match ``token`` (itself included)."""
    token = normalize_text(token)
    return {token, *_INDEX.get(token, set())}


def expand_query(text: str) -> list[set[str]]:
    """One OR group per meaningful token of ``text``.

    The groups are meant to be AND-ed by the caller. An unknown token is its
    own singleton group, so search never gets *wider* than the user asked.
    """
    return [expand_token(token) for token in tokenize(text)]


def suggestions_for(prefix: str, limit: int = 8) -> list[str]:
    """Vocabulary entries starting with ``prefix`` (normalized)."""
    prefix = normalize_text(prefix)
    if not prefix:
        return []
    matches = sorted(term for term in VOCABULARY if term.startswith(prefix))
    return matches[:limit]
