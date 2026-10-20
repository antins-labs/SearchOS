"""技能资产、运行时，以及 intent → pipeline 创建链路。"""
from pathlib import Path
from typing import Any

from searchos.skills.catalog.registry import SkillRegistry
from searchos.skills.core.schema import parse_skill_file, parse_skill_text
from searchos.skills.intent import SkillSignal, SkillRequest, infer_requests
from searchos.skills.pipeline import PipelineResult, run_pipeline


async def generate_skills(signal: SkillSignal, *, library_path: str | Path | None = None,
                          intent_model: Any = None, builder_model: Any = None,
                          model_name: str | None = None,
                          categories: tuple[str, ...] = ('access', 'strategy', 'orchestrator'),
                          max_requests: int | None = None, min_opens: int = 3, obs_chars: int = 800,
                          subtask_runner: Any = None, judge_model: Any = None,
                          trial_root: str | Path | None = None, on_progress: Any = None) -> list[PipelineResult]:
    """外部信号 → 生成请求 → 对应 pipeline；单个请求失败不影响后续请求。"""
    if library_path is None:
        from searchos.config.settings import settings
        library_path = settings.skill_library_path
    async def emit(event):
        if on_progress is not None:
            await on_progress(event)

    await emit({'stage': 'intent'})
    requests = await infer_requests(signal, model=intent_model, library_path=library_path,
                                    categories=categories, max_requests=max_requests,
                                    min_opens=min_opens, obs_chars=obs_chars)
    from dataclasses import asdict
    await emit({'stage': 'planned', 'requests': [asdict(r) for r in requests]})
    results = []
    for index, request in enumerate(requests):
        await emit({'stage': 'pipeline', 'index': index})
        async def on_draft(path):
            await emit({'stage': 'pipeline', 'index': index, 'draft_path': str(path)})
        result = await run_pipeline(request, library_path=library_path, model=builder_model,
                                    model_name=model_name, subtask_runner=subtask_runner,
                                    subtask=request.subtask if signal.kind == 'trace' else None,
                                    judge_model=judge_model, trial_root=trial_root, on_draft=on_draft)
        results.append(result)
        await emit({'stage': 'result', 'index': index, 'result': result.to_report()})
    return results


async def generate_from_trace(trace_path: str | Path, *, library_path: str | Path,
                              model: Any = None, max_requests: int | None = None,
                              on_progress: Any = None):
    """任务结束后的独立生成；验证不再向已结束的搜索会话写入证据。"""
    from searchos.skills.pipeline.strategy.standalone import run_standalone_subtask
    return await generate_skills(
        SkillSignal('trace', trace_path=trace_path), library_path=library_path,
        intent_model=model, builder_model=model, max_requests=max_requests,
        categories=('access', 'strategy', 'orchestrator'),
        subtask_runner=run_standalone_subtask,
        on_progress=on_progress,
    )


__all__ = ['SkillRegistry', 'parse_skill_file', 'parse_skill_text', 'SkillSignal',
           'SkillRequest', 'infer_requests', 'PipelineResult', 'run_pipeline', 'generate_skills', 'generate_from_trace']
