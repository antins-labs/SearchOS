"""创建接口仅接收意图，不允许客户端指定本机文件或执行命令。"""
from fastapi import APIRouter, HTTPException, Query
from typing import Literal
from pydantic import BaseModel, Field
from api.skill_creation_jobs import CreationInput, jobs

router = APIRouter(prefix='/api/skills/creations', tags=['skills'])


@router.post('', status_code=202)
async def create_skill(request: CreationInput):
    return jobs.create(request)


@router.get('')
async def list_creations():
    return jobs.list()


class DeleteCreations(BaseModel, extra='forbid'):
    ids: list[str] = Field(min_length=1, max_length=100)


@router.post('/delete')
async def delete_creations(request: DeleteCreations):
    try:
        return {'deleted': jobs.delete(request.ids)}
    except FileNotFoundError:
        raise HTTPException(404, '创建记录不存在，请刷新后重试')
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@router.delete('/{job_id}')
async def delete_creation(job_id: str):
    return await delete_creations(DeleteCreations(ids=[job_id]))


@router.post('/{job_id}/cancel')
async def cancel_creation(job_id: str):
    try:
        return await jobs.cancel(job_id)
    except FileNotFoundError:
        raise HTTPException(404, '创建记录不存在')
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@router.get('/{job_id}')
async def get_creation(job_id: str):
    try:
        return jobs.read(job_id)
    except (ValueError, FileNotFoundError):
        raise HTTPException(404, '创建作业不存在')


@router.post('/{job_id}/requests/{index}/resume', status_code=202)
async def resume_creation(job_id: str, index: int):
    try:
        return jobs.resume(job_id, index)
    except FileNotFoundError:
        raise HTTPException(404, '创建记录或草稿不存在')
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@router.get('/{job_id}/requests/{index}/draft')
def get_draft(job_id: str, index: int):
    from api.skill_creation_drafts import detail
    try:
        return detail(jobs.read(job_id), jobs.root, index)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(404, str(exc))


@router.get('/{job_id}/requests/{index}/draft/file')
def get_draft_file(job_id: str, index: int, path: str):
    from api.skill_creation_drafts import read_file
    try:
        return read_file(jobs.read(job_id), jobs.root, index, path)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc))


class DraftEdit(BaseModel, extra='forbid'):
    path: str = Field(min_length=1, max_length=512)
    content: str = Field(max_length=256000)
    revision: str = Field(min_length=1, max_length=256)


@router.put('/{job_id}/requests/{index}/draft/file')
async def put_draft_file(job_id: str, index: int, edit: DraftEdit):
    from api.skill_creation_drafts import edit_file
    try:
        job = jobs.read(job_id)
        jobs.assert_editable(job, index)
        return edit_file(job, jobs.root, index, **edit.model_dump())
    except FileNotFoundError:
        raise HTTPException(404, '草稿不存在')
    except ValueError as exc:
        raise HTTPException(409, str(exc))


library_router = APIRouter(prefix='/api/skills/library', tags=['skills'])


@library_router.get('')
def list_library():
    from api.skill_library import catalog
    return catalog()


@library_router.get('/query')
def query_library(q: str = Query(default='', max_length=500),
                  category: Literal['all', 'access', 'strategy', 'orchestrator'] = 'all',
                  page: int = Query(default=1, ge=1),
                  page_size: int = Query(default=24, ge=1, le=100)):
    from api.skill_library import query_catalog
    return query_catalog(q=q, category=category, page=page, page_size=page_size)


@library_router.get('/{category}/{name}')
def get_skill(category: str, name: str):
    from api.skill_library import detail
    return detail(category, name)


@library_router.get('/{category}/{name}/file')
def get_skill_file(category: str, name: str, path: str):
    from api.skill_library import read_file
    return read_file(category, name, path)
