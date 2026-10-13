#!/usr/bin/env python3
"""本地评测对话查看器；仅使用 Python 标准库。"""
import argparse
import ast
import json
import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs


def normalize(value, depth=0):
    if depth > 12:
        return value
    if isinstance(value, str) and value.strip().startswith(('{', '[')):
        for parser in (json.loads, ast.literal_eval):
            try:
                parsed = parser(value)
                if isinstance(parsed, (dict, list)):
                    return normalize(parsed, depth + 1)
            except (ValueError, SyntaxError, TypeError, RecursionError):
                pass
    if isinstance(value, dict):
        return {k: normalize(v, depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize(v, depth + 1) for v in value]
    return value


def build_index(root):
    cases = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d not in {'pages', 'turn_snapshots', 'conversations', 'preprocess_cache', 'agent_logs', 'skills', 'intermediate', 'blackboard'}]
        p = Path(directory)
        if 'eval_result.json' not in files and not (p/'session/conversations').is_dir() and not (p/'session/trajectory.jsonl').is_file():
            continue
        try:
            d = {}
            status = '未出评测结果'
            if 'eval_result.json' in files:
                try:
                    d = json.loads((p/'eval_result.json').read_text())
                    status = '已出评测结果'
                except (ValueError, OSError):
                    status = '评测文件暂不可读'
            conv = p/'session/conversations'
            agents = sorted(f.stem for f in conv.glob('*.json'))
            if not d.get('question'):
                try:
                    d['question'] = json.loads((conv/'orchestrator.json').read_text()).get('task', '')
                except (ValueError, OSError):
                    pass
                if not d.get('question'):
                    try:
                        with (p/'session/trajectory.jsonl').open() as log:
                            for _, line in zip(range(20), log):
                                try:
                                    event = json.loads(line)
                                except ValueError:
                                    continue
                                if event.get('type') == 'task_start':
                                    d['question'] = event.get('query', '')
                                    break
                    except OSError:
                        pass
            benchmark = d.get('benchmark') or ('widesearch' if p.name.startswith('ws_') else 'gisa' if p.name.isdigit() else 'unknown')
            cases.append(dict(path=p.relative_to(root).as_posix(), id=str(d.get('id', p.name)),
                              benchmark=benchmark, question=d.get('question', ''), status=status,
                              agents=agents, trajectory=(p/'session/trajectory.jsonl').is_file(),
                              metrics={k: v for k, v in (d.get('metrics') or {}).items() if isinstance(v, (int, float, bool))}, elapsed_s=d.get('elapsed_s'),
                              coverage=d.get('coverage'), tokens=(d.get('token_usage') or {}).get('total_tokens'),
                              started_at=d.get('started_at', ''), error=d.get('error'),
                              answers=[n for n in ['raw_answer.md', 'reformatted.md'] if (p/n).is_file()]))
        except (ValueError, OSError, AttributeError) as e:
            print(f'跳过 {p}: {e}')
    # 未评分运行可能只记录改写后的任务；只有题号对应唯一已评分题目时才归并。
    questions = {}
    for c in cases:
        if c['status'] == '已出评测结果' and c['question']:
            questions.setdefault((c['benchmark'], c['id']), set()).add(c['question'])
    for c in cases:
        known = questions.get((c['benchmark'], c['id']), set())
        if c['status'] != '已出评测结果' and len(known) == 1:
            c['question'] = next(iter(known))
    return sorted(cases, key=lambda c: (c['started_at'], c['path']), reverse=True)


def make_handler(root):
    root = root.resolve()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            req = urlparse(self.path)
            try:
                if req.path in ('/', '/index.html'):
                    body = Path(__file__).with_name('index.html').read_bytes()
                    mime = 'text/html; charset=utf-8'
                elif req.path == '/api/index':
                    body = json.dumps(build_index(root), ensure_ascii=False).encode()
                    mime = 'application/json; charset=utf-8'
                elif req.path == '/api/file':
                    rel = parse_qs(req.query).get('path', [''])[0]
                    p = (root / rel).resolve()
                    if root not in p.parents or not p.is_file():
                        self.send_error(404); return
                    allowed = p.name in {'eval_result.json', 'trajectory.jsonl', 'raw_answer.md', 'reformatted.md'} or (p.parent.name == 'conversations' and p.suffix == '.json')
                    if not allowed:
                        self.send_error(403); return
                    raw = p.read_text()
                    if p.suffix == '.json':
                        raw = json.dumps(normalize(json.loads(raw)), ensure_ascii=False)
                    body = raw.encode()
                    mime = 'text/plain; charset=utf-8'
                else:
                    self.send_error(404); return
                self.send_response(200)
                self.send_header('Content-Type', mime)
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()
                self.wfile.write(body)
            except (OSError, ValueError) as e:
                self.send_error(500, str(e))
    return Handler


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2]/'eval_results')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        parser.error(f'目录不存在: {root}')
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(root))
    print(f'评测查看器: http://127.0.0.1:{args.port}  数据: {root}', flush=True)
    server.serve_forever()
