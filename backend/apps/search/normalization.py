"""Search text normalization for Arabic, French and Latin spellings.

Phase 15 (docs/todo.md) needs one normal form that makes the *same* listing
findable however the buyer types it:

* Arabic diacritics and tatweel are dropped, hamza forms collapse to a bare
  alef, alef maqsura becomes ya and ta marbuta becomes ha - the well-known
  Arabic IR normalization set.
* French accents and ligatures are folded (``Citroën`` → ``citroen``), so a
  keyboard without accents is not a second-class search.
* The Arabic definite article is stripped token by token (``الهاتف`` →
  ``هاتف``) because it is almost never the discriminating part of a query.
* Arabic-Indic digits become ASCII digits (``١٢٨`` → ``128``), since model
  numbers are typed on a Latin keypad more often than not.

The module is pure standard library: the catalogue builder (indexing) and the
query builder (searching) both use exactly this code, which is what keeps
"stored" and "searched" from drifting apart.
"""

from __future__ import annotations

import re
import unicodedata

#: Any Arabic letter; used to decide whether a token needs transliteration.
ARABIC_LETTERS = re.compile(r"[\u0600-\u06ff]")

#: Harakat, tanwin, shadda, sukun, superscript alef, Quranic marks, tatweel.
_ARABIC_MARKS = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed\u0640]")

#: Token characters: Latin letters/digits and Arabic letters/digits. Anything
#: else (punctuation, emoji, currency symbols) is a separator.
_TOKEN = re.compile(r"[0-9a-z\u0660-\u0669\u06f0-\u06f9\u0600-\u06ff]+")

_LATIN_FOLD = str.maketrans(
    {
        "œ": "oe",
        "æ": "ae",
        "ß": "ss",
        "ø": "o",
        "đ": "d",
        "ł": "l",
        "’": " ",
        "‘": " ",
        "`": " ",
        "'": " ",
        "«": " ",
        "»": " ",
    }
)

_ARABIC_DIGITS = str.maketrans(
    {**{chr(0x0660 + i): str(i) for i in range(10)}, **{chr(0x06F0 + i): str(i) for i in range(10)}}
)

_ARABIC_CHAR_MAP = str.maketrans(
    {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",
        "ى": "ي",
        "ئ": "ي",
        "ؤ": "و",
        "ة": "ه",
        "ڤ": "ف",
        "ڨ": "ق",
        "گ": "ك",
        "پ": "ب",
        "چ": "ش",
        "ژ": "ز",
    }
)

#: Words that carry no meaning for matching. Kept deliberately short: an
#: over-eager list (``car``, ``new``, brand names...) would delete the signal.
STOPWORDS = frozenset(
    {
        # French
        "le",
        "la",
        "les",
        "un",
        "une",
        "des",
        "du",
        "de",
        "d",
        "et",
        "ou",
        "en",
        "au",
        "aux",
        "avec",
        "pour",
        "par",
        "sur",
        "dans",
        "ce",
        "cette",
        "ces",
        "mon",
        "ma",
        "mes",
        "votre",
        "vos",
        "nos",
        "est",
        "sont",
        # English
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "for",
        "with",
        "in",
        "on",
        "to",
        "is",
        "are",
        # Arabic (after normalization: ة→ه, أ→ا ...)
        "في",
        "من",
        "علي",
        "الي",
        "عن",
        "مع",
        "هذا",
        "هزه",
        "هو",
        "هي",
        "ان",
        "او",
        "و",
        "ب",
        "ل",
        "ك",
        "ال",
    }
)


def strip_arabic_marks(text: str) -> str:
    return _ARABIC_MARKS.sub("", text)


def normalize_arabic(text: str) -> str:
    """Fold Arabic orthography to one comparable spelling."""
    return strip_arabic_marks(text).translate(_ARABIC_CHAR_MAP)


def fold_latin(text: str) -> str:
    """Lowercase and remove French accents/ligatures (``É`` → ``e``)."""
    folded = unicodedata.normalize("NFKD", text.casefold().translate(_LATIN_FOLD))
    return "".join(char for char in folded if not unicodedata.combining(char))


def normalize_text(text: str) -> str:
    """The canonical form stored in ``Product.search_document``.

    The return value is a space-joined token string: no punctuation, no
    stopwords, no Arabic article prefix, digits in ASCII. Both the indexer and
    the query builder call this, so their token streams are identical.
    """
    if not text:
        return ""
    text = normalize_arabic(str(text).translate(_ARABIC_DIGITS))
    text = fold_latin(text)
    tokens = []
    for token in _TOKEN.findall(text):
        token = _strip_arabic_article(token)
        if token and token not in STOPWORDS:
            tokens.append(token)
    return " ".join(tokens)


def _strip_arabic_article(token: str) -> str:
    """Drop a leading ``ال`` from a long enough Arabic token.

    ``الة``/``اله`` are left alone: stripping them leaves a two-letter stump
    that matches too much. Non-Arabic tokens pass through untouched.
    """
    if len(token) > 4 and token.startswith("ال") and ARABIC_LETTERS.match(token):
        return token[2:]
    return token


def tokenize(text: str) -> list[str]:
    """Normalized, de-duplicated tokens in first-seen order."""
    seen: dict[str, None] = {}
    for token in normalize_text(text).split():
        seen.setdefault(token, None)
    return list(seen)


def has_arabic(text: str) -> bool:
    return bool(ARABIC_LETTERS.search(text or ""))


def transliterate(text: str) -> str:
    """A Latin approximation of Arabic text (``هاتف`` → ``hatf``).

    Deliberately letter-by-letter rather than a phonetic scheme: it exists so
    an Arabic listing also matches a Latin *typo* through trigram similarity,
    not to be a readable romanization. Long vowels are not invented.
    """
    table = {
        "ا": "a",
        "ب": "b",
        "ت": "t",
        "ث": "th",
        "ج": "j",
        "ح": "h",
        "خ": "kh",
        "د": "d",
        "ذ": "dh",
        "ر": "r",
        "ز": "z",
        "س": "s",
        "ش": "ch",
        "ص": "s",
        "ض": "d",
        "ط": "t",
        "ظ": "z",
        "ع": "a",
        "غ": "gh",
        "ف": "f",
        "ق": "q",
        "ك": "k",
        "ل": "l",
        "م": "m",
        "ن": "n",
        "ه": "h",
        "و": "w",
        "ي": "y",
        "ء": "",
    }
    return "".join(table.get(char, char) for char in normalize_arabic(text))


def latin_tokens(text: str) -> str:
    """Transliterations of the Arabic tokens in ``text``, space-joined."""
    output = []
    for token in normalize_text(text).split():
        if has_arabic(token):
            latin = transliterate(token)
            if latin and latin not in STOPWORDS:
                output.append(latin)
    return " ".join(output)
