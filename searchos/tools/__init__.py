"""Tool system (paper §Tool System) — grouped by agent assignment.

One module per tool group; each exposes a ``get_*_tools()`` factory:

- ``simple_browser`` — search / open / find (Search, Explore)
- ``schema`` — schema + entity CRUD (Orchestrator)
- ``tasks`` — sub-agent task queue (Orchestrator)
- ``writer`` — outline management (Writer)
- ``socm_read`` — read-only SOCM views (Writer)
- ``skill_catalog`` — list / load skills (Search, Writer)

``search_state`` holds the per-task workspace / agent ContextVars the
tools read from.
"""
