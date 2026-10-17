"""技能资产浏览；与运行时启用开关独立，只读取包内可分发文件。"""
from pathlib import Path
import re
import yaml

from fastapi import HTTPException
from api.deps import _REPO_ROOT
from api.skills.catalog import SKILL_CATEGORIES, skill_enabled
from searchos.skills.core.schema import find_skill_entry, parse_skill_text
from searchos.skills.packaging import package_files


def library_root():
    from searchos.config.settings import settings
    root = Path(settings.skill_library_path)
    return (root if root.is_absolute() else _REPO_ROOT / root).resolve()


def package(category, name):
    if category not in SKILL_CATEGORIES or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', name):
        raise HTTPException(404, '技能不存在')
    root = library_root()
    path = root / category / name
    if path.is_symlink() or (root / category).is_symlink() or not path.is_dir() or not path.resolve().is_relative_to(root):
        raise HTTPException(404, '技能不存在')
    return path


def metadata(path, category):
    entry = find_skill_entry(path)
    if entry.is_symlink() or entry.stat().st_size > 262144:
        raise ValueError('Invalid skill entry')
    raw = entry.read_text(encoding='utf-8')
    skill = parse_skill_text(raw, strict=entry.name == 'SKILL.md')
    return dict(name=path.name, category=category, description=skill.meta.description or skill.meta.trigger or '',
                availability=skill.meta.availability.value, enabled=skill_enabled(category, skill.meta.name),
                package_format='portable' if entry.name == 'SKILL.md' else 'legacy',
                entry=entry.name, body=skill.body, source=raw)


def catalog(*, include_body=False):
    items = []
    for category in SKILL_CATEGORIES:
        folder = library_root() / category
        if not folder.is_dir() or folder.is_symlink():
            continue
        for path in sorted(folder.iterdir()):
            if path.name.startswith(('.', '_')) or not path.is_dir() or path.is_symlink():
                continue
            try:
                item = metadata(path, category)
                items.append({k: v for k, v in item.items() if k != 'source' and (include_body or k != 'body')})
            except (ValueError, OSError, yaml.YAMLError):
                continue
    return items


def detail(category, name):
    path = package(category, name)
    try:
        item = metadata(path, category)
        item['files'] = [p.as_posix() for p in package_files(path)]
        return item
    except (ValueError, OSError, yaml.YAMLError) as exc:
        raise HTTPException(422, '技能包无法读取') from exc


def read_file(category, name, filename):
    path = package(category, name)
    try:
        if filename not in {p.as_posix() for p in package_files(path)}:
            raise HTTPException(404, '文件不在技能包中')
        target = path / filename
        if not target.resolve().is_relative_to(path.resolve()):
            raise HTTPException(404, '文件不在技能包中')
        if target.stat().st_size > 262144:
            raise HTTPException(413, '文件过大，暂不支持预览')
        content = target.read_text(encoding='utf-8')
        if '\x00' in content:
            raise HTTPException(415, '只支持文本文件预览')
        return {'path': filename, 'content': content}
    except UnicodeError as exc:
        raise HTTPException(415, '只支持文本文件预览') from exc
    except (ValueError, OSError, yaml.YAMLError) as exc:
        raise HTTPException(404, '文件无法读取') from exc


def query_catalog(*, q='', category='all', page=1, page_size=24):
    terms = q.casefold().split()
    matches = [item for item in catalog(include_body=True)
               if all(term in f"{item['name']} {item['description']} {item['body']}".casefold() for term in terms)]
    counts = {key: sum(item['category'] == key for item in matches) for key in SKILL_CATEGORIES}
    counts['all'] = len(matches)
    filtered = [item for item in matches if category == 'all' or item['category'] == category]
    filtered.sort(key=lambda item: (item['name'].casefold(), item['category']))
    total = len(filtered)
    pages = (total + page_size - 1) // page_size
    current = min(page, max(1, pages))
    items = [{k: v for k, v in item.items() if k != 'body'}
             for item in filtered[(current - 1) * page_size:current * page_size]]
    return dict(items=items, total=total, page=current, page_size=page_size, pages=pages, counts=counts)
