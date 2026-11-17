"""阅读工具说明与后续导航。"""

CATALOG_TOOL = """Browse the authorized local catalog for source references.
path: INDEX.md (default), subindexes/<topic>.md or documents/<id>.md; reuse catalog_path.
query: case-insensitive text; searches all catalogs when path is omitted, otherwise that catalog.
Follow returned local:// references with local_open or local_find."""

OPEN_TOOL = """Read a bounded text window or original image from an authorized local source.
ref_id: copy a versioned local:// reference from the catalog or search result.
The all reference reads indexed document sections together; legacy refs support text reads.
loc: zero-based character offset. max_chars: window size, 1–20000. Follow the returned Next offset.
view: text for a transcript; original for a PDF page or image frame (requires a versioned ref).
representation_id: reuse the returned selector, or primary; omit for original view."""

FIND_TOOL = """Find case-insensitive substrings in one local source and return character offsets.
ref_id: copy a local:// source reference. pattern: a string or list of alternatives.
representation_id: optional selector; preserve it in local_open so offsets remain valid.
Read matching source windows before citing them."""

INDEXED_DOCUMENT = """Indexed document text: ref_id="{ref_id}"
Read short documents with local_open(max_chars=20000); follow Next offsets for longer text.
Use section refs for focused questions. Check source coverage warnings.

{catalog}"""

NEXT_WINDOW = (
    'Next: local_open(ref_id="{ref_id}", loc={offset}, max_chars={max_chars}, '
    "representation_id={representation!r})"
)
OPEN_MATCH = (
    'Open a match with local_open(ref_id="{ref_id}", loc=<match loc>, max_chars=6000, '
    "representation_id={representation!r})."
)
