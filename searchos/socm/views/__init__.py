"""SOCM projection φ(M): build a read-only SearchStateSnapshot, render it
to role-specific text for each consumer (orchestrator / search / extraction).
"""

from searchos.socm.views.render import (
    render_compact_summary,
    render_discovery_view,
    render_extraction_snapshot,
    render_fill_snapshot,
    render_known_pk_list,
    render_orchestrator_view,
    render_search_agent_view,
)
from searchos.socm.views.snapshot import (
    CellInfo,
    FrontierSnapshot,
    RowStatus,
    SearchStateSnapshot,
    TableSnapshot,
)

__all__ = [
    "SearchStateSnapshot", "TableSnapshot", "RowStatus", "CellInfo", "FrontierSnapshot",
    "render_orchestrator_view", "render_search_agent_view", "render_discovery_view",
    "render_extraction_snapshot", "render_fill_snapshot", "render_known_pk_list",
    "render_compact_summary",
]
