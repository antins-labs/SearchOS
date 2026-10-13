"""SearchOS agents (paper §Agent Roles).

Orchestrator + explore / web search / local search / writer sub-agents. Each
role package assembles its own toolset via ``get_tools()``; ``runtime`` holds
the shared ReAct loop factory and session context.
"""
