"""Pipeline：按请求类别生成包，校验后发布到对应技能库。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import logging
import tempfile
from typing import Any, Literal

from searchos.skills.intent.models import SkillRequest
from searchos.skills.pipeline.store import publish_package
from searchos.skills.pipeline.valid import validate_request_package

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineResult:
    request: SkillRequest
    status: Literal['installed', 'build_failed', 'validation_failed', 'error']
    path: Path | None = None
    error: str = ''
    trial_path: Path | None = None

    def to_report(self) -> dict[str, str]:
        report = {'category': self.request.category.value, 'name': self.request.name,
                  'status': self.status, 'reason': self.request.reason, 'action': self.request.action}
        if self.request.host:
            report['host'] = self.request.host
        if self.path is not None:
            report['path'] = str(self.path)
        if self.error:
            report['error'] = self.error
        if self.trial_path:
            report['trial_path'] = str(self.trial_path)
        return report



async def run_pipeline(request: SkillRequest, *, library_path: str | Path,
                       model: Any = None, model_name: str | None = None,
                       subtask: str | None = None, subtask_runner: Any = None,
                       judge_model: Any = None, trial_root: str | Path | None = None,
                       trial_timeout_s: float = 120) -> PipelineResult:
    """一个请求对应一次生成；不解析用户问题或轨迹，也不进行运行时选择。"""
    library = Path(library_path)
    category_root = library / request.category.value
    trial_path = None
    try:
        from searchos.skills.catalog.registry import SkillRegistry
        from searchos.skills.packaging import package_fingerprint
        registry = SkillRegistry()
        registry.load_directory(library)
        existing = next((s for s in registry.list_all()
                         if s.meta.category == request.category and s.meta.name == request.name), None)
        final = Path(existing.file_path).parent if existing else category_root / request.name
        if request.action == 'update' and existing is None:
            raise ValueError('update target does not exist')
        if request.action == 'create' and final.exists():
            raise ValueError('skill already exists; use an explicit update request')
        old_host = str(existing.meta.metadata.get('host', '')).lower() if existing else ''
        if old_host and request.host and old_host != request.host:
            raise ValueError('update cannot change the target host')
        original_hash = package_fingerprint(final) if existing else None
        category_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=f'.pipeline_{request.name}_', dir=category_root) as temporary:
            candidate = Path(temporary) / request.name
            diagnostics = {}
            if request.category.value == 'access':
                from searchos.skills.pipeline.access.run import build_skill
                from uuid import uuid4
                record_dir = (Path(trial_root) if trial_root else library.parent / '.skill-trials') / request.name / uuid4().hex
                trial_path = record_dir / 'result.json'
                host = request.host or old_host
                built = await build_skill(host=host, probe_urls=list(request.probe_urls) or ([f'https://{host}/'] if host else []),
                                          notes=request.description + '\n' + request.reason,
                                          output_dir=candidate, builder_model=model, model=model_name, diagnostics=diagnostics, record_dir=record_dir,
                                          existing_package=final if existing else None)
            else:
                from searchos.skills.pipeline.text.run import build_text_skill
                built = await build_text_skill(request, output_dir=candidate, model=model, model_name=model_name,
                                               existing_package=final if existing else None, subtask=subtask)
            if built is None:
                import json
                error = json.dumps(diagnostics, ensure_ascii=False) if diagnostics else '生成器未产出通过校验的技能包；请检查模型配置或验证日志。'
                if trial_path is not None or trial_root is not None:
                    from uuid import uuid4
                    from searchos.skills.pipeline.strategy.trial import save_record
                    trial_path = trial_path or Path(trial_root) / request.name / uuid4().hex / 'result.json'
                    save_record(trial_path, {'status': 'build_failed', 'reason': error, 'diagnostics': diagnostics})
                return PipelineResult(request, 'build_failed', error=error, trial_path=trial_path)
            if Path(built).resolve() != candidate.resolve():
                raise ValueError('pipeline must return the requested candidate package')
            validate_request_package(candidate, request)
            if request.category.value == 'strategy':
                from searchos.skills.pipeline.strategy.trial import validate_strategy
                from searchos.tools.search_state import _current_task_var
                task = subtask if subtask is not None else _current_task_var.get() or request.subtask
                accepted, trial_path, reason = await validate_strategy(
                    candidate, subtask=task, library_path=library, runner=subtask_runner,
                    judge_model=judge_model, results_root=Path(trial_root) if trial_root else None,
                    timeout_s=trial_timeout_s)
                if not accepted:
                    return PipelineResult(request, 'validation_failed', error=reason, trial_path=trial_path)
            if original_hash is not None and package_fingerprint(final) != original_hash:
                raise ValueError('installed skill changed during validation; retry update against the new version')
            if original_hash is None and final.exists():
                raise ValueError('skill was installed during generation; retry as an update')
            publish_package(candidate, final)
            if request.category.value == 'access' and trial_path is not None:
                from searchos.skills.pipeline.strategy.trial import save_record
                save_record(trial_path, {'status': 'installed', 'path': str(final), 'diagnostics': diagnostics})
            return PipelineResult(request, 'installed', path=final, trial_path=trial_path)
    except Exception as exc:
        logger.warning('skill pipeline failed: %s/%s: %s', request.category.value, request.name, exc)
        if request.category.value == 'access' and trial_path is not None:
            from searchos.skills.pipeline.strategy.trial import save_record
            save_record(trial_path, {'status': 'error', 'error_type': type(exc).__name__, 'diagnostics': diagnostics})
        return PipelineResult(request, 'error', error=str(exc), trial_path=trial_path)


__all__ = ['PipelineResult', 'run_pipeline']
