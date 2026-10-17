"""SOCM 只读工具入口；读取快照，不修改共享状态。"""

from searchos.tools.socm_read.coverage import coverage_summary, read_coverage
from searchos.tools.socm_read.evidence import read_evidence, resolve_cell_provenance
from searchos.tools.socm_read.frontier import list_frontier, read_task_report

__all__ = [
    "coverage_summary", "read_coverage", "read_evidence", "resolve_cell_provenance",
    "list_frontier", "read_task_report", "get_socm_read_tools",
]


def get_socm_read_tools() -> list:
    """Return SOCM read-only view tools for writer wiring."""
    return [read_coverage, read_evidence, resolve_cell_provenance, list_frontier, read_task_report]
