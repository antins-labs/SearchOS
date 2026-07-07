"""Extraction layer (paper §3.3) — the ONLY writer of Evidence / Coverage.

Intercepts browser + access-skill results, parses them into ``EvidenceNode``
records, and atomically updates ``CoverageMap`` via
``WorkspaceManager.atomic_update_state``.
"""

from searchos.harness.middleware.extraction.evidence_extraction import (
    EvidenceExtractionMiddleware,
)

ExtractionMiddleware = EvidenceExtractionMiddleware  # plan §三 alias

__all__ = ["EvidenceExtractionMiddleware", "ExtractionMiddleware"]
