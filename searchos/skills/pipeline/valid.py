"""入库前校验包与原始生成请求一致。"""
from pathlib import Path

from searchos.skills.intent.models import SkillRequest
from searchos.skills.packaging import validate_package


def validate_request_package(candidate: Path, request: SkillRequest):
    skill = validate_package(candidate, expected_name=request.name)
    if skill.meta.category != request.category or not skill.body.strip():
        raise ValueError('generated package category/body does not match the request')
    if request.category.value == 'access':
        from searchos.skills.pipeline.access.validation.checks import validate_access_structure
        report = validate_access_structure(candidate, request.name, require_host=bool(request.host),
                                           expected_host=request.host or None)
        if not report.get('package_valid'):
            raise ValueError(report.get('error', 'access package structure is invalid'))
    if skill.meta.metadata.get('searchos-category') != request.category.value:
        raise ValueError('metadata.searchos-category must match the request')
    if request.host and str(skill.meta.metadata.get('host', '')).lower() != request.host:
        raise ValueError('generated host does not match the request')
    return skill
