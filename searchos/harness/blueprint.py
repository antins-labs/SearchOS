"""SearchBlueprint: agent configuration with guides/sensors.

Extends the concept of AgentBlueprint to include Harness-specific
configurations: which guides, sensors, budget, and skills to use.

Model selection is no longer carried on the blueprint — every model use
site resolves through ``model_factory.get_model_for(role)`` against
``settings.profiles`` + ``settings.roles``.
"""

from __future__ import annotations

from pydantic import Field

from searchos.config.settings import settings
from searchos.util.base_model import CamelModel


class BudgetConfig(CamelModel):
    max_time_s: int = settings.default_max_time_s


class HarnessConfig(CamelModel):
    budget_warning_ratio: float = settings.budget_warning_ratio
    enable_trajectory_logging: bool = True


class SearchBlueprint(CamelModel):
    """Configuration for creating a search agent with Harness."""

    name: str = "search_agent"
    system_prompt: str = ""  # overridden by prompts module

    # Harness
    harness: HarnessConfig = Field(default_factory=HarnessConfig)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)

    # Skills
    skill_library_path: str = "searchos/skills/library"
    skill_max_inject: int = 2

    # Tools
    enable_web_search: bool = True
    enable_code_executor: bool = True
    # file_ops: provided by deepagents FilesystemMiddleware (no toggle needed)
    enable_browser: bool = False  # Phase 3

    # Workers (Phase 2)
    enable_teams: bool = False
    max_workers: int = 5
