"""Read ``.po`` catalogues and write ``.mo`` binaries with no tooling.

Django's ``compilemessages`` shells out to GNU ``gettext``'s ``msgfmt``, which
is not part of a stock Windows/Python install — and this machine does not have
it. An API that promises to answer in Arabic cannot have its error catalogue
depend on a build tool that may or may not exist on the next contributor's
machine, so the parts of the MO format we need (no plurals, no hash table) are
implemented here instead — about a hundred lines, no dependencies.

``tests/test_locale.py`` re-runs this compiler over every checked-in catalogue
and fails if a committed ``.mo`` no longer matches its ``.po`` source, so the
two can never drift.

Format (GNU gettext binary MO, little-endian):

    magic | revision | count | originals-table | translations-table
          | hash-size | hash-offset
    originals-table : count * (length, offset)
    translations-table: count * (length, offset)
    ...bytes...

The entry whose ``msgid`` is the empty string carries the catalogue metadata
(charset, plural rules); gettext reads it first, which is why the header is
not optional here.
"""

from __future__ import annotations

import ast
import struct
from pathlib import Path

#: Little-endian MO magic, as bytes: 0x950412de written least-significant
#: first. ``gettext`` uses it to decide the byte order of the whole file.
MO_MAGIC = 0x950412DE

#: What the header entry must say for Django/Python to decode the rest.
DEFAULT_CHARSET = "utf-8"


class CatalogueError(ValueError):
    """A malformed ``.po`` file, or one using a feature this compiler refuses."""


def _unquote(raw: str, *, where: str) -> str:
    """Undo C-style quoting. ``.po`` strings are C strings, and Python's
    escapes are the same ones for the subset we emit (``\\n``, ``\\"``,
    ``\\\\``, ``\\t``).

    ``raw`` arrives with its delimiting quotes still on — including the empty
    ``""`` of the header entry — so they are removed before evaluating, rather
    than wrapped in a second pair (which would turn ``""`` into a triple
    quote and blow up).
    """
    text = raw.strip()
    if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
        text = text[1:-1]
    try:
        value = ast.literal_eval(f'"{text}"')
    except (SyntaxError, ValueError) as exc:
        raise CatalogueError(f"{where}: cannot parse quoted string {raw!r}: {exc}") from exc
    if not isinstance(value, str):  # pragma: no cover - literal_eval safety net
        raise CatalogueError(f"{where}: expected a string, got {value!r}")
    return value


def parse_po(text: str, *, where: str = "<po>") -> dict[str, str]:
    """Parse a ``.po`` file into ``{msgid: msgstr}``.

    Supports what an error catalogue needs: comments (skipped), ``msgid`` /
    ``msgstr`` pairs, multiline continuations, and the empty-``msgid`` header.
    Plural forms are refused loudly rather than silently half-parsed — see the
    module docstring.
    """
    entries: dict[str, str] = {}
    msgid: str | None = None
    msgstr: str | None = None
    reading: str | None = None  # which field continuation lines extend

    def flush() -> None:
        if msgid is not None and msgstr is not None:
            entries[msgid] = msgstr

    for number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        here = f"{where}:{number}"

        if not line or line.startswith("#"):
            continue
        if line.startswith(("msgid_plural", "msgstr[", "msgid_plural ")):
            raise CatalogueError(
                f"{here}: plural forms are not supported by core.mofile "
                "(the API's error catalogue has none; use Django's own "
                "compilemessages for a catalogue that grows one)"
            )
        if line.startswith("msgid "):
            flush()
            msgid = _unquote(line[len("msgid ") :].strip(), where=here)
            msgstr = None
            reading = "msgid"
        elif line.startswith("msgstr "):
            msgstr = _unquote(line[len("msgstr ") :].strip(), where=here)
            reading = "msgstr"
        elif line.startswith('"') and line.endswith('"'):
            if reading is None:
                raise CatalogueError(f"{here}: stray continuation line {line!r}")
            piece = _unquote(line, where=here)
            if reading == "msgid":
                msgid = (msgid or "") + piece
            else:
                msgstr = (msgstr or "") + piece
        else:
            raise CatalogueError(f"{here}: unrecognised line {line!r}")

    flush()
    if not entries:
        raise CatalogueError(f"{where}: no entries found")
    return entries


def build_mo(entries: dict[str, str]) -> bytes:
    """Serialise ``{msgid: msgstr}`` as an MO binary (UTF-8, little-endian).

    Entries are sorted by msgid because the GNU spec says so and other tools
    (``msgfmt -c``, gettext's own binary search) rely on it; Python's
    ``gettext`` would not care.
    """
    if "" not in entries:
        # Without the header entry Python decodes the rest as ASCII, which
        # would mangle every translated message.
        entries = {**entries, "": DEFAULT_CHARSET}

    items = sorted(entries.items(), key=lambda pair: pair[0].encode(DEFAULT_CHARSET))

    ids = bytearray()
    values = bytearray()
    id_offsets: list[tuple[int, int]] = []
    value_offsets: list[tuple[int, int]] = []

    for msgid, msgstr in items:
        encoded_id = msgid.encode(DEFAULT_CHARSET)
        encoded_value = msgstr.encode(DEFAULT_CHARSET)
        id_offsets.append((len(ids), len(encoded_id)))
        ids += encoded_id + b"\x00"
        value_offsets.append((len(values), len(encoded_value)))
        values += encoded_value + b"\x00"

    count = len(items)
    # 7 header words (28 bytes), then two tables of count * (length, offset).
    header_size = 7 * 4
    id_table_offset = header_size
    value_table_offset = id_table_offset + count * 8
    id_data_offset = value_table_offset + count * 8
    value_data_offset = id_data_offset + len(ids)

    output = bytearray()
    output += struct.pack(
        "<IIIIIII",
        MO_MAGIC,
        0,  # revision: major 0 only, or gettext refuses the file
        count,
        id_table_offset,
        value_table_offset,
        0,  # hash table size: 0 = omitted (permitted by the spec)
        0,  # hash table offset
    )
    for offset, length in id_offsets:
        output += struct.pack("<II", length, offset + id_data_offset)
    for offset, length in value_offsets:
        output += struct.pack("<II", length, offset + value_data_offset)
    output += ids
    output += values
    return bytes(output)


def compile_po(po_path: Path, mo_path: Path | None = None) -> Path:
    """Compile ``po_path`` to its sibling ``.mo`` and return the written path.

    The file is rewritten unconditionally: the caller decides whether to keep
    the result (the management command does; the test compares bytes).
    """
    po_path = Path(po_path)
    target = Path(mo_path) if mo_path else po_path.with_suffix(".mo")

    entries = parse_po(po_path.read_text(encoding="utf-8"), where=str(po_path))
    if "" not in entries:
        entries = {"": DEFAULT_CHARSET, **entries}

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(build_mo(entries))
    return target


def iter_catalogues(locale_paths) -> list[tuple[Path, Path]]:
    """Every ``<locale>/<lang>/LC_MESSAGES/<domain>.po`` under the given roots."""
    found = []
    for root in locale_paths:
        for po_path in sorted(Path(root).glob("*/LC_MESSAGES/*.po")):
            found.append((po_path, po_path.with_suffix(".mo")))
    return found
