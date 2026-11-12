"""Bilingual normalization, transliteration and synonym expansion (Phase 15).

These are pure functions: no database, no Django. Pinning them here is what
keeps the *indexed* form and the *queried* form identical as the synonym table
grows.
"""

from apps.search.normalization import (
    fold_latin,
    latin_tokens,
    normalize_text,
    tokenize,
    transliterate,
)
from apps.search.synonyms import expand_query, expand_token


def test_arabic_orthography_is_folded_to_one_spelling():
    # Hamza forms, alef maqsura, ta marbuta, harakat and tatweel all collapse.
    assert normalize_text("  الهَاتِفُ الأَحْمَر  ") == "هاتف احمر"
    assert normalize_text("مَدْرَسَةٌ") == "مدرسه"
    assert normalize_text("هـــاتف") == "هاتف"
    assert normalize_text("مصطفى") == "مصطفي"


def test_arabic_definite_article_is_stripped_but_short_words_survive():
    assert normalize_text("السيارة") == "سياره"
    assert normalize_text("الة") == "اله"  # too short to strip safely


def test_arabic_indic_digits_become_ascii():
    assert normalize_text("سامسونج ١٢٨") == "سامسونج 128"


def test_french_accents_and_ligatures_fold():
    assert fold_latin("Citroën C4 ÉLÉGANTE") == "citroen c4 elegante"
    assert normalize_text("Œuf à l'ancienne") == "oeuf l ancienne"


def test_stopwords_are_removed_but_content_words_survive():
    assert tokenize("la voiture de mon père") == ["voiture", "pere"]
    assert tokenize("the phone and the charger") == ["phone", "charger"]


def test_transliteration_makes_arabic_reachable_from_a_latin_keyboard():
    assert transliterate("هاتف") == "hatf"
    assert "hatf" in latin_tokens("هاتف سامسونج").split()
    assert transliterate("سيارة") == "syarh"


def test_synonyms_cover_arabic_french_and_darija():
    assert "voiture" in expand_token("tomobile")
    assert "telephone" in expand_token("hatif")
    assert "voiture" in expand_token("سيارة")
    assert "samsung" in expand_token("سامسونج")


def test_expand_query_keeps_one_group_per_token():
    groups = expand_query("samsung telephone")
    assert len(groups) == 2
    assert any("samsung" in group for group in groups)
    assert any("hatif" in group for group in groups)


def test_unknown_words_expand_only_to_themselves():
    assert expand_token("kayak") == {"kayak"}
    assert expand_query("") == []
