"""Catalog topics, summaries, and Markdown navigation."""

from searchos.local.catalog.prompts import (
    CATALOG_PROMPT_VERSION,
    CLASSIFY_SYSTEM_PROMPT,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    TOPIC_SUMMARY_SYSTEM_PROMPT,
    classify_document,
    revise_subindex,
)
from searchos.local.catalog.service import (
    CatalogClient,
    CatalogDocument,
    CatalogMarkdownStore,
    CatalogService,
    ModelCatalogClient,
    Subindex,
    make_subindex_id,
)

__all__ = [
    "CATALOG_PROMPT_VERSION",
    "CLASSIFY_SYSTEM_PROMPT",
    "CatalogClient",
    "CatalogDocument",
    "CatalogMarkdownStore",
    "CatalogService",
    "ModelCatalogClient",
    "PROMPT_VERSION",
    "SYSTEM_PROMPT",
    "Subindex",
    "TOPIC_SUMMARY_SYSTEM_PROMPT",
    "classify_document",
    "make_subindex_id",
    "revise_subindex",
]
