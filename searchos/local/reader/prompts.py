"""阅读工具说明与后续导航。"""

CATALOG_TOOL = """\
Find documents in the authorized catalog and their local:// references. The catalog names documents and where to open them. What a document says is in the text local_open returns.
path selects INDEX.md by default, or subindexes/<topic>.md or documents/<id>.md; reuse a returned catalog_path.
query is a case-insensitive literal: omit path to search every catalog in scope, or set path to search that catalog only.
Follow returned local:// references with local_open or local_find before citing them."""

OPEN_TOOL = """\
Read one bounded text window, or the original PDF page or image, from an authorized local source.
Copy ref_id from a catalog or find result. The indexed-document all reference reads that document's sections as one text; other references read the cited span.
loc is a zero-based character offset and max_chars is 1–20000; continue from the returned Next offset until the needed span is covered.
view=text returns the transcript. view=original requires a versioned ref and is for figures, scanned tables, and exact visual values; do not pass representation_id with it.
For text, reuse the returned representation_id, or primary, so later offsets stay on the same text."""

FIND_TOOL = """\
Find literal, case-insensitive substrings in one local source and return character offsets.
pattern is one string or a list of alternatives, not a regular expression.
Copy ref_id from the catalog or an earlier read, and pass that same representation_id to local_open so the offsets stay valid.
No local source matches means those strings are not in this text. Read a match with local_open before citing it."""

NEXT_WINDOW = (
    'Next: local_open(ref_id="{ref_id}", loc={offset}, max_chars={max_chars}, '
    "representation_id={representation!r})"
)
OPEN_MATCH = (
    'Read this match before citing it: local_open(ref_id="{ref_id}", loc=<match loc>, '
    "max_chars=6000, representation_id={representation!r})."
)

INDEXED_DOCUMENT = """\
Indexed document text. ref_id="{ref_id}"
Read a short document with local_open(max_chars=20000). For longer text, follow each returned Next offset, or open a section reference for a focused question.
If Metadata contains warnings, do not treat this read as the whole document.

{catalog}"""
