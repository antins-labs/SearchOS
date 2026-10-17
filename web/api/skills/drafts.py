"""创建记录中的草稿阅读与编辑；客户端只传作业、请求序号和包内相对路径。"""
from pathlib import Path
from collections import deque
import json
import tempfile
import shutil

from api.deps import _REPO_ROOT
from searchos.skills.pipeline.drafts import load_draft, package_path, save_draft


def draft_pointer(job: dict, root: Path, index: int) -> Path:
    if index < 0 or index >= len(job.get('requests', [])):
        raise ValueError('请求序号不存在')
    result = next((r for r in job.get('results', []) if r.get('name') == job['requests'][index]['name']
                   and r.get('category') == job['requests'][index].get('category')), {})
    value = job.get('drafts', {}).get(str(index)) or result.get('draft_path')
    if not value:
        raise ValueError('没有可恢复的草稿')
    pointer = Path(value)
    if not pointer.is_absolute():
        pointer = _REPO_ROOT / pointer
    if not pointer.resolve().is_relative_to((root / 'trials' / job['id']).resolve()):
        raise ValueError('草稿不属于当前创建记录')
    if not pointer.is_file():
        raise ValueError('草稿尚未保存')
    return pointer


def detail(job, root, index):
    pointer = draft_pointer(job, root, index)
    _, data = load_draft(pointer)
    diagnostics = pointer.parent / 'builder.json'
    events = pointer.parent / 'events.jsonl'
    recent = []
    if events.exists():
        with events.open(encoding='utf-8') as handle:
            for line in deque(handle, maxlen=40):
                try:
                    recent.append(json.loads(line))
                except ValueError:
                    continue  # 运行中最后一个事件可能尚未写完。
    return {'name': data['name'], 'revision': data['package'], 'files': list(data['files']),
            'examples': data['examples'], 'validation': data['validation'],
            'diagnostics': json.loads(diagnostics.read_text()) if diagnostics.exists() else {},
            'events': recent}


def read_file(job, root, index, path):
    pointer = draft_pointer(job, root, index)
    package, data = load_draft(pointer)
    relative = str(package_path(path))
    if relative not in data['files']:
        raise ValueError('文件不属于草稿')
    target = package / relative
    if target.stat().st_size > 256_000:
        raise ValueError('文件过大，不能在线编辑')
    try:
        content = target.read_text(encoding='utf-8')
    except UnicodeError:
        raise ValueError('仅支持编辑 UTF-8 文本')
    return {'path': relative, 'content': content, 'revision': data['package']}


def edit_file(job, root, index, *, path, content, revision):
    pointer = draft_pointer(job, root, index)
    package, data = load_draft(pointer)
    if data['package'] != revision:
        raise ValueError('草稿已更新，请重新读取后编辑')
    relative = str(package_path(path))
    if relative not in data['files']:
        raise ValueError('文件不属于草稿')
    if len(content.encode('utf-8')) > 256_000:
        raise ValueError('文件过大，不能在线编辑')
    with tempfile.TemporaryDirectory(dir=pointer.parent) as tmp:
        edited = Path(tmp) / data['name']
        shutil.copytree(package, edited)
        (edited / relative).write_text(content, encoding='utf-8')
        save_draft(pointer.parent, edited, data['files'], name=data['name'], examples=data['examples'],
                   require_host=data['require_host'], validation={'valid': False, 'stage': 'edited',
                   'error': '草稿已手动编辑，继续修复时将重新验证。', 'previous': data['validation']})
    return detail(job, root, index)
