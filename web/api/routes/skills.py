"""创建接口仅接收意图，不允许客户端指定本机文件或执行命令。"""
from fastapi import APIRouter, HTTPException, Query
from typing import Literal
from api.skill_creation_jobs import CreationInput, jobs

router = APIRouter(prefix='/api/skills/creations', tags=['skills'])


@router.post('', status_code=202)
async def create_skill(request: CreationInput):
    return jobs.create(request)


@router.get('')
async def list_creations():
    return jobs.list()


@router.get('/{job_id}')
async def get_creation(job_id: str):
    try:
        return jobs.read(job_id)
    except (ValueError, FileNotFoundError):
        raise HTTPException(404, '创建作业不存在')


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
