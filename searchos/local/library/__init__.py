"""WebUI local-library facade: persistence, topics, ingest, and QA."""

from searchos.local.library.ingest import merge_origins as _merge_origins
from searchos.local.library.qa import CitationStream as _CitationStream
from searchos.local.library.qa import LocalAnswer
from searchos.local.library.service import LocalLibraryRecord, LocalLibraryService
from searchos.local.refs import LOCAL_LINK_RE as _LOCAL_LINK_RE

__all__ = [
    "LocalAnswer",
    "LocalLibraryRecord",
    "LocalLibraryService",
    "_CitationStream",
    "_LOCAL_LINK_RE",
    "_merge_origins",
]
