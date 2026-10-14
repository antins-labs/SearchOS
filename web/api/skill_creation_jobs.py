"""技能创建作业：持久化进度，串行生成，重启后显式标记中断。"""
from __future__ import annotations

import asyncio
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator
from typing import Literal
from urllib.parse import urlsplit

from api.deps import _REPO_ROOT, LOCAL_DATA_ROOT
from searchos.skills import SkillSignal, SkillRequest, generate_skills, run_pipeline
from searchos.skills.pipeline.strategy.standalone import run_standalone_subtask


class CreationInput(BaseModel, extra='forbid'):
    kind: Literal['site', 'task', 'trace']
    text: str = Field(default='', max_length=64000)
    site: str = Field(default='', max_length=2048)
    categories: list[Literal['access', 'strategy', 'orchestrator']] = Field(
        default_factory=lambda: ['access', 'strategy', 'orchestrator'], min_length=1, max_length=3)
    max_requests: int = Field(default=3, ge=1, le=10)

    @model_validator(mode='after')
    def validate_signal(self):
        self.signal()
        return self

    def signal(self):
        if self.kind == 'site':
            url = self.site.strip()
            if '://' not in url:
                url = 'https://' + url
            parsed = urlsplit(url)
            if (parsed.scheme not in {'http', 'https'} or not parsed.hostname
                    or parsed.username or parsed.password or parsed.fragment
                    or any(c.isspace() for c in url)):
                raise ValueError('请输入有效的 HTTP(S) 站点地址，不含凭据或片段')
            if 'access' not in self.categories:
                raise ValueError('站点意图需要 access 类别')
            return SkillSignal('site', text=self.text, host=parsed.hostname, probe_urls=(url,))
        if self.site:
            raise ValueError('只有站点意图接受 site')
        return SkillSignal(self.kind, text=self.text)


def now():
    return datetime.now(timezone.utc).isoformat()


class CreationJobs:
    def __init__(self, root: Path):
        self.root = root
        self.tasks: dict[str, asyncio.Task] = {}
        self.lock = asyncio.Lock()

    def path(self, job_id):
        if not re.fullmatch(r'[a-f0-9]{32}', job_id):
            raise ValueError('无效的创建作业 ID')
        return self.root / f'{job_id}.json'

    def write(self, job):
        self.root.mkdir(parents=True, exist_ok=True)
        job['updated_at'] = now()
        path = self.path(job['id'])
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(job, ensure_ascii=False, indent=2))
        temp.replace(path)

    def read(self, job_id):
        job = json.loads(self.path(job_id).read_text())
        from api.skill_creation_drafts import draft_pointer
        for index, request in enumerate(job.get('requests', [])):
            try:
                draft_pointer(job, self.root, index)
                request['has_draft'] = True
            except ValueError:
                request['has_draft'] = False
        return job

    def assert_editable(self, job, index):
        if job['status'] in {'running', 'queued'}:
            raise ValueError('创建进行中，不能编辑或续修草稿')
        request = job['requests'][index] if 0 <= index < len(job.get('requests', [])) else None
        if request is None:
            raise ValueError('请求序号不存在')
        if any(r.get('name') == request['name'] and r.get('category') == request['category']
               and r.get('status') == 'installed' for r in job['results']):
            raise ValueError('该技能已入库，请发起新的更新请求')
        for active in self.list():
            if active['status'] in {'queued', 'running'} and active.get('resume_of') == {'job_id': job['id'], 'index': index}:
                raise ValueError('该草稿正在续修，请查看新的续修记录')

    def resume(self, job_id, index):
        from api.skill_creation_drafts import draft_pointer
        from searchos.skills.pipeline.drafts import load_draft
        parent = self.read(job_id)
        for active in self.list():
            if active['status'] in {'queued', 'running'} and active.get('resume_of') == {'job_id': job_id, 'index': index}:
                return active
        self.assert_editable(parent, index)
        pointer = draft_pointer(parent, self.root, index)
        load_draft(pointer)
        request = {k: v for k, v in parent['requests'][index].items() if k in SkillRequest.__dataclass_fields__}
        SkillRequest(**request)
        job = dict(id=uuid4().hex, input=parent['input'], status='queued', stage='repair',
                   requests=[request], results=[], current_index=None, error='', created_at=now(),
                   resume_of={'job_id': job_id, 'index': index}, resume_draft=str(pointer))
        self.write(job)
        task = asyncio.create_task(self.run(job))
        self.tasks[job['id']] = task
        task.add_done_callback(lambda _: self.tasks.pop(job['id'], None))
        return job

    def _records(self):
        jobs = []
        for path in self.root.glob('*.json'):
            try:
                jobs.append(self.read(path.stem))
            except (ValueError, OSError):
                continue
        return jobs

    def list(self):
        return sorted(self._records(), key=lambda j: j['created_at'], reverse=True)[:100]

    def delete(self, job_ids: list[str]):
        """只按作业 ID 清理自有记录目录；绝不使用结果中的技能或日志路径。"""
        ids = list(dict.fromkeys(job_ids))
        if not 1 <= len(ids) <= 100:
            raise ValueError('每次请选择 1 到 100 条记录')
        records = [self.read(identifier) for identifier in ids]
        active = [job for job in self._records() if job['status'] in {'queued', 'running'}]
        for identifier, job in zip(ids, records):
            task = self.tasks.get(identifier)
            if job['status'] in {'queued', 'running'} or (task is not None and not task.done()):
                raise ValueError('请先停止创建，再删除记录')
            if any((child.get('resume_of') or {}).get('job_id') == identifier for child in active):
                raise ValueError('该记录的草稿正在续修，请先停止续修任务')
            for path in (self.path(identifier), self.root / 'trials', self.root / 'trials' / identifier):
                if path.is_symlink() or not path.resolve().is_relative_to(self.root.resolve()):
                    raise ValueError('记录目录异常，不能删除')
        # 整批先校验，避免遇到运行中记录时只删掉了部分选择。
        for identifier in ids:
            trial = self.root / 'trials' / identifier
            if trial.exists():
                shutil.rmtree(trial)
            self.path(identifier).unlink()
        return ids

    async def cancel(self, job_id: str):
        job = self.read(job_id)
        if job['status'] not in {'queued', 'running'}:
            return job
        task = self.tasks.get(job_id)
        if task is None:
            raise ValueError('找不到当前执行任务，请刷新记录后重试')
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        # 排队协程可能尚未进入 run/finally；读取最终记录后补齐停止状态。
        job = self.read(job_id)
        if job['status'] in {'queued', 'running', 'interrupted'}:
            job.update(status='interrupted', current_index=None,
                       error='用户已停止创建；草稿和已入库技能保留。')
            self.write(job)
        return job

    def recover(self):
        for path in self.root.glob('*.json'):
            try:
                job = self.read(path.stem)
            except (ValueError, OSError):
                continue
            if job['status'] in {'queued', 'running'}:
                job.update(status='interrupted', error='服务已重启，创建中断；已保存的草稿可继续修复，已入库技能保留。')
                self.write(job)

    def create(self, request: CreationInput):
        for existing in self.list():
            if existing['status'] in {'queued', 'running'} and existing['input'] == request.model_dump():
                return existing
        job = dict(id=uuid4().hex, input=request.model_dump(), status='queued', stage='queued',
                   requests=[], results=[], current_index=None, error='', created_at=now())
        self.write(job)
        task = asyncio.create_task(self.run(job))
        self.tasks[job['id']] = task
        task.add_done_callback(lambda _: self.tasks.pop(job['id'], None))
        return job

    async def run(self, job):
        try:
            async with self.lock:
                from searchos.config.settings import settings
                library = Path(settings.skill_library_path)
                if not library.is_absolute():
                    library = _REPO_ROOT / library
                job.update(status='running')
                self.write(job)

                async def progress(event):
                    job['stage'] = event['stage']
                    if 'requests' in event:
                        job['requests'] = event['requests']
                    if 'index' in event:
                        job['current_index'] = event['index']
                    if 'result' in event:
                        job['results'].append(event['result'])
                    if 'draft_path' in event:
                        job.setdefault('drafts', {})[str(event['index'])] = event['draft_path']
                    self.write(job)

                request = CreationInput.model_validate(job['input'])
                async with asyncio.timeout(3600):
                    if job.get('resume_draft'):
                        async def on_draft(path):
                            await progress({'stage': 'repair', 'index': 0, 'draft_path': str(path)})
                        job.update(stage='repair', current_index=0)
                        self.write(job)
                        selected = SkillRequest(**job['requests'][0])
                        result = await run_pipeline(selected, library_path=library,
                            resume_draft=Path(job['resume_draft']), subtask=selected.subtask,
                            subtask_runner=run_standalone_subtask, on_draft=on_draft,
                            trial_root=self.root / 'trials' / job['id'])
                        results = [result]
                        await progress({'stage': 'result', 'index': 0, 'result': result.to_report()})
                    else:
                        results = await generate_skills(request.signal(), library_path=library,
                            categories=tuple(request.categories), max_requests=request.max_requests,
                            subtask_runner=run_standalone_subtask,
                            trial_root=self.root / 'trials' / job['id'], on_progress=progress)
                installed = sum(r.status == 'installed' for r in results)
                job.update(status=('completed' if installed == len(results) else 'partial' if installed else 'failed'),
                           stage='done', current_index=None)
        except asyncio.CancelledError:
            job.update(status='interrupted', error='服务停止，创建中断；已保存的草稿可继续修复，已入库技能保留。')
            raise
        except Exception as exc:
            job.update(status='failed', error=str(exc) or type(exc).__name__)
        finally:
            self.write(job)

    async def stop(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        # 未开始执行的协程不会进入 finally，也要持久化其中断状态。
        self.recover()


jobs = CreationJobs(Path(LOCAL_DATA_ROOT) / 'skill_creation_jobs')
