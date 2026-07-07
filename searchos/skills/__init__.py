"""Self-Evolving Skill System (paper §Skills).

子包与论文概念的映射：

- ``library/``   — 三层技能库（§Skill Hierarchy）：orchestrator / strategy / access
- ``core/``      — 数据模型与解析：Skill/SkillMeta、skill.md frontmatter、
                   SkillContext 执行契约、anti-pattern 索引
- ``catalog/``   — 检索与注入（§Skill Retrieval）：registry 加载索引，
                   router 做 access top-k 预筛与 orchestrator playbook 渲染
- ``runtime/``   — 执行（§T0-T3 四层抽取）：executor 运行时 + 网络出口 shim
- ``evolution/`` — 在线进化（§Online Skill Evolution）：轨迹挖掘 + 动态烘焙
"""

from searchos.skills.catalog.registry import SkillRegistry
from searchos.skills.core.schema import parse_skill_file, parse_skill_text

__all__ = [
    "SkillRegistry",
    "parse_skill_file",
    "parse_skill_text",
]
