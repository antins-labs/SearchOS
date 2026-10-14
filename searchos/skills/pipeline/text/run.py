"""Strategy / Orchestrator 说明包生成；结构校验不代替效果试验。"""
from __future__ import annotations

import json
import yaml
from pathlib import Path
from typing import Any

from searchos.skills.intent.models import SkillRequest
from searchos.skills.pipeline.text.prompt import system_prompt
from searchos.skills.pipeline.text.valid import validate_text_package


async def build_text_skill(request: SkillRequest, *, output_dir: Path,
                           model: Any = None, model_name: str | None = None,
                           existing_package: Path | None = None,
                           subtask: str | None = None,
                           checkpoint: Any = None,
                           repair_feedback: dict | None = None,
                           max_attempts: int = 3) -> Path | None:
    if request.category.value not in {'strategy', 'orchestrator'}:
        raise ValueError('text pipeline only accepts strategy/orchestrator requests')
    if model is None:
        from searchos.config.models import get_model_for
        model = get_model_for('skill_evolver', model_override=model_name)
    output_dir.mkdir(parents=True, exist_ok=True)
    previous = ''
    if existing_package is not None:
        from searchos.skills.packaging import package_files
        import shutil
        for relative in package_files(existing_package):
            target = output_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(existing_package / relative, target)
        previous = (existing_package / 'SKILL.md').read_text(encoding='utf-8')
    from langchain_core.messages import HumanMessage, SystemMessage
    from searchos.tools.search_state import _current_task_var
    messages = [SystemMessage(content=system_prompt(request.category.value)),
                HumanMessage(content=json.dumps({'name': request.name, 'category': request.category.value,
                                                 'description': request.description, 'reason': request.reason,
                                                 'action': request.action, 'existing_skill': previous,
                                                 'subtask': subtask if subtask is not None else _current_task_var.get() or request.subtask}, ensure_ascii=False))]
    if previous:
        messages.append(HumanMessage(content='根据能力缺口更新已有 SKILL.md，保留原有有效能力、约束及资源引用；返回完整新版本。'))
    if repair_feedback is not None:
        messages.append(HumanMessage(content='继续修复保存的候选草稿，针对上次失败原因修改：\n' + json.dumps(repair_feedback, ensure_ascii=False)))
    for _ in range(max_attempts):
        response = await model.ainvoke(messages)
        content = response.content if hasattr(response, 'content') else str(response)
        if isinstance(content, list):
            content = ''.join(b.get('text', '') if isinstance(b, dict) else str(b) for b in content)
        content = str(content).strip()
        if content.startswith('```'):
            content = content.split('\n', 1)[1].rsplit('```', 1)[0].strip()
        (output_dir / 'SKILL.md').write_text(content + '\n', encoding='utf-8')
        if checkpoint:
            checkpoint({'valid': False, 'stage': 'pending_validation'})
        try:
            validate_text_package(output_dir, request)
            return output_dir
        except (ValueError, OSError, yaml.YAMLError) as exc:
            if checkpoint:
                checkpoint({'valid': False, 'stage': 'package', 'error': str(exc)})
            messages.extend([response, HumanMessage(content=f'校验失败，请修正完整 SKILL.md：{exc}')])
    return None
