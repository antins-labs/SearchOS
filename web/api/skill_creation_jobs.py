"""技能创建作业：持久化进度，串行生成，重启后显式标记中断。"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator
from typing import Literal
from urllib.parse import urlsplit

from api.deps import _REPO_ROOT, LOCAL_DATA_ROOT
from searchos.skills import SkillSignal, generate_skills
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
        return json.loads(self.path(job_id).read_text())

    def list(self):
        jobs = []
        for path in self.root.glob('*.json'):
            try:
                jobs.append(self.read(path.stem))
            except (ValueError, OSError):
                continue
        return sorted(jobs, key=lambda j: j['created_at'], reverse=True)[:100]

    def recover(self):
        for path in self.root.glob('*.json'):
            try:
                job = self.read(path.stem)
            except (ValueError, OSError):
                continue
            if job['status'] in {'queued', 'running'}:
                job.update(status='interrupted', error='服务已重启，创建中断；可重新提交，已入库技能会自动跳过。')
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
                    self.write(job)

                request = CreationInput.model_validate(job['input'])
                async with asyncio.timeout(3600):
                    results = await generate_skills(request.signal(), library_path=library,
                        categories=tuple(request.categories), max_requests=request.max_requests,
                        subtask_runner=run_standalone_subtask,
                        trial_root=self.root / 'trials' / job['id'], on_progress=progress)
                installed = sum(r.status == 'installed' for r in results)
                job.update(status=('completed' if installed == len(results) else 'partial' if installed else 'failed'),
                           stage='done', current_index=None)
        except asyncio.CancelledError:
            job.update(status='interrupted', error='服务停止，创建中断；已入库技能保留。')
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
