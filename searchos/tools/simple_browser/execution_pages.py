"""将执行快照注册为普通保存页面；阅读统一使用 open/find。"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from searchos.socm.provenance import result_source_urls
from searchos.tools.simple_browser.render import PageContents
from searchos.tools.simple_browser.skill_pages import format_skill_result
from searchos.tools.simple_browser.state import _get_browser, _persist_page, _read_page_from_disk

MAX_TEXT_BYTES = 10_000_000


def resolve_execution_root(url: str) -> PageContents | None:
    """执行根地址只解析宿主保存的索引，保留结果页的规范来源身份。"""
    if not re.fullmatch(r"skill://[^/?#]+/[^/?#]+/?", url):
        return None
    prefix = url.rstrip('/') + '/'
    browser = _get_browser()
    index = browser.get_page_by_url(prefix + 'index') or _read_page_from_disk(prefix + 'index')
    if index is None or index.metadata.get('kind') != 'execution_index':
        return None
    target = index.metadata.get('primary_page_url', '')
    if isinstance(target, str) and target.startswith(prefix):
        primary = browser.get_page_by_url(target) or _read_page_from_disk(target)
        if primary is not None:
            return primary
    # 旧记录没有主页面指针；索引仍给出完整结果地址，不猜测文件名。
    return index


def _fixture(value):
    if isinstance(value, dict):
        return bool(value.get('fixture') or value.get('input_mode') == 'fixture') or any(_fixture(v) for v in value.values())
    if isinstance(value, list):
        return any(_fixture(v) for v in value)
    return False


def register_execution_pages(result: dict, binding: dict, saved: Path, task_key: str) -> dict:
    """内容只从宿主保存的快照读取；页面类型不接受脚本自报覆盖。"""
    from searchos.tools.skill_execution import _safe_file

    browser = _get_browser()
    prefix = f"skill://{binding['name']}/{result['execution_id']}"
    pages, skipped = [], []

    def publish(key, title, content, kind, digest='', *, primary_page_url='', source_urls=()):
        url = prefix + '/' + key
        metadata = {'kind': kind, 'evidence_eligible': kind == 'skill_result',
                    'execution_id': result['execution_id'], 'package_hash': binding['package_hash'],
                    'producer_task': task_key, 'artifact_hash': digest,
                    'page_content_hash': hashlib.sha256(content.encode()).hexdigest(),
                    'source_urls': list(source_urls)}
        if primary_page_url:
            metadata['primary_page_url'] = primary_page_url
        page = PageContents(url=url, title=title, text=content, metadata=metadata)
        page_id = _persist_page(url, page)
        if not page_id:
            raise OSError("could not persist execution page")
        browser.add_page(page)
        browser.page_ids[url] = page_id
        return {'url': url, 'title': title, 'kind': kind}

    def render(raw, title, key, *, diagnostic=False, digest=''):
        text = raw.decode('utf-8')
        if '\x00' in text:
            raise ValueError('binary content')
        try:
            value = json.loads(text)
        except ValueError:
            value = None
        if value is not None:
            text = format_skill_result(value)
        failed = isinstance(value, dict) and (value.get('error') or value.get('success') is False)
        kind = 'diagnostic' if diagnostic or failed else ('fixture' if _fixture(value) else 'skill_result')
        pages.append(publish(key, title, text, kind, digest,
                             source_urls=result_source_urls(value) if kind == 'skill_result' else ()))

    for item in result.get('artifacts', []):
        try:
            path = _safe_file(saved / 'artifacts', item['path'])
            if path.stat().st_size > MAX_TEXT_BYTES:
                raise ValueError('text page size limit exceeded; process with a bundled script')
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != item['sha256']:
                raise ValueError('saved content hash mismatch')
            key = hashlib.sha256(item['path'].encode()).hexdigest()[:20]
            diagnostic = result['status'] != 'completed' or path.suffix.lower() == '.log'
            render(raw, item['path'], key, diagnostic=diagnostic, digest=item['sha256'])
        except (ValueError, OSError, KeyError, RecursionError) as exc:
            skipped.append({'path': item.get('path', ''), 'reason': str(exc)})

    has_files = bool(result.get('artifacts'))
    for stream in ('stdout', 'stderr'):
        text = result.get(stream, '')
        log = saved / f'{stream}.log'
        if log.is_file() and log.stat().st_size <= MAX_TEXT_BYTES:
            text = log.read_text(encoding='utf-8', errors='replace')
        if not text.strip():
            continue
        # Plain stdout may be help/progress logs. A complete JSON stdout result
        # without output files retains the existing structured skill-result path.
        try:
            json.loads(text)
            json_output = True
        except (ValueError, RecursionError):
            json_output = False
        diagnostic = stream == 'stderr' or has_files or not json_output or result['status'] != 'completed'
        try:
            render(text.encode(), stream, stream, diagnostic=diagnostic)
        except (ValueError, RecursionError) as exc:
            skipped.append({"path": stream, "reason": str(exc)})

    index_text = '\n'.join([f"Execution: {result['execution_id']}", f"Status: {result['status']}", '',
                            *[f"{p['title']} ({p['kind']}): {p['url']}" for p in pages],
                            *[f"Not rendered: {p['path']} — {p['reason']}" for p in skipped]])
    primary = next((p for p in pages if p['kind'] == 'skill_result'), pages[0] if pages else None)
    index = publish('index', 'Skill execution: ' + binding['name'], index_text, 'execution_index',
                    primary_page_url=primary['url'] if primary else '')
    primary = primary or index
    # find() 使用当前页；注册索引不能把阅读光标留在不参与抽取的目录页。
    browser.add_page(browser.pages[primary['url']])
    return {'page_url': primary['url'], 'index_page_url': index['url'],
            'pages': pages[:20], 'pages_total': len(pages), 'unrendered': skipped[:20]}
