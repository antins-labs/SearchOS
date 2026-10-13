"""说明包校验仅确认结构和类别，不声称验证方法的效果。"""
from pathlib import Path
from searchos.skills.intent.models import SkillRequest
from searchos.skills.packaging import validate_package


def validate_text_package(directory: Path, request: SkillRequest):
    skill = validate_package(directory)
    if skill.meta.category != request.category or skill.meta.metadata.get('searchos-category') != request.category.value:
        raise ValueError('metadata.searchos-category must match the request')
    if not skill.body.strip():
        raise ValueError('instructions must not be empty')
    return skill
