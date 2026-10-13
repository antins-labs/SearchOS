"""已迁移的内置技能名称映射；不改写未知的第三方名称。"""
from functools import lru_cache
import json
from pathlib import Path


@lru_cache(maxsize=1)
def legacy_names() -> dict[str, str]:
    return json.loads(Path(__file__).with_name('legacy_names.json').read_text(encoding='utf-8'))


def canonical_skill_name(name: str) -> str:
    return legacy_names().get(name, name)


def canonical_skill_names(names):
    return {canonical_skill_name(name) for name in names}
