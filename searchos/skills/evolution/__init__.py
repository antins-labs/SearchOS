"""在线技能进化（paper §Online Skill Evolution）.

Triggered at session end (opt-in via ``settings.enable_access_skill_generation``):
``host_miner`` triages a run's trajectory for hosts worth a dedicated extractor,
``dynamic_builder`` drives an LLM to probe each and bake a complete skill into
the library.
"""

from searchos.skills.evolution.dynamic_builder import build_skill
from searchos.skills.evolution.host_miner import generate_access_skills_from_trace

__all__ = ["build_skill", "generate_access_skills_from_trace"]
