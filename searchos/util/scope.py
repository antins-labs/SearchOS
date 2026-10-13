"""从任务文本匹配实体范围。"""


def match_entities_in_task(
    task_text: str, entities: list[str], *, require_first_component: bool = False,
) -> set[str]:
    """忽略大小写匹配实体名，或复合主键中至少两字符的分量。

    require_first_component 用于任务投影：复合实体必须匹配首个主键分量，
    避免同名专业等次级分量把任务扩展到其他学校。
    使用子串匹配，不展开范围，也不检查词边界。
    """
    if not task_text or not entities:
        return set()
    haystack = task_text.lower()
    matched: set[str] = set()
    for entity in entities:
        name = entity.lower()
        if name in haystack:
            matched.add(entity)
            continue
        if "|" in name:
            components = name.split("|")
            if require_first_component:
                components = components[:1]
            parts = [part.strip() for part in components if len(part.strip()) >= 2]
            if any(part in haystack for part in parts):
                matched.add(entity)
    return matched
