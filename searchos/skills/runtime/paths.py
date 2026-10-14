"""会话内的技能存储路径；旧会话沿用原目录以保留绑定与执行回执。"""

from pathlib import Path


_COMPONENTS = ("packages", "bindings", "calls", "executions", "work")


def skill_workspace_dir(root: Path, component: str) -> Path:
    """新会话收拢到 skills/；整个旧会话统一沿用 skill_* 布局。"""
    if component not in _COMPONENTS:
        raise ValueError(f"Unknown skill workspace component: {component}")
    if any((root / f"skill_{name}").is_dir() for name in _COMPONENTS):
        return root / f"skill_{component}"
    return root / "skills" / component
