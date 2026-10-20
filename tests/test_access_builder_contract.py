"""通用 Access Builder 的生成、修复与发布契约。"""
from pathlib import Path
import json

import pytest
from langchain_core.messages import AIMessage
from searchos.skills.pipeline.access.tools import BuilderWorkspace
from searchos.skills.pipeline.access.run import build_skill
from searchos.skills.pipeline.access.valid import package_is_complete as _portable_skill_is_complete


@pytest.mark.asyncio
async def test_builder_exec_uses_agent_runtime_and_separate_workdir(tmp_path, monkeypatch):
    from searchos.skills.runtime import command_runtime
    workspace = BuilderWorkspace(tmp_path / 'example-com')
    calls = []
    async def run(package, argv, **kwargs):
        calls.append((package, argv, kwargs))
        return {'status': 'completed', 'exit_code': 0}
    monkeypatch.setattr(command_runtime, 'run_command', run)
    try:
        await workspace.dispatch('exec', {'argv': ['python', 'scripts/search.py']})
        await workspace.dispatch('exec', {'argv': ['python', 'scripts/parse.py']})
        assert calls[0][2]['work_dir'] == calls[1][2]['work_dir']
        assert not calls[0][2]['work_dir'].is_relative_to(workspace.output_dir)
    finally:
        workspace.close()


@pytest.mark.asyncio
async def test_builder_repairs_failed_validation_and_publishes_only_package(tmp_path, monkeypatch):
    from searchos.skills.runtime import command_runtime
    seen = []
    class Model:
        count = 0
        def bind_tools(self, tools):
            assert {'exec', 'validate_skill', 'register_example'} <= {t['function']['name'] for t in tools}
            return self
        async def ainvoke(self, messages):
            self.count += 1
            seen.append(messages)
            if self.count == 1:
                return AIMessage(content='', tool_calls=[
                    {'id': '1', 'name': 'write_file', 'args': {'path': 'SKILL.md', 'content': '---\nname: example-com\ndescription: 查询记录\nmetadata:\n  searchos-category: access\n  host: example.com\n---\n运行 scripts/search.py。'}},
                    {'id': '2', 'name': 'write_file', 'args': {'path': 'scripts/search.py', 'content': 'print(1)'}},
                ])
            if self.count == 3:
                assert 'register at least one' in messages[-1].content
                return AIMessage(content='', tool_calls=[{'id': '3', 'name': 'register_example', 'args': {'argv': ['python', 'scripts/search.py'], 'output': '', 'records_key': 'records'}}])
            return AIMessage(content='完成')
    async def run(package, argv, **kwargs):
        # A probe/execution byproduct must not contaminate the installed package.
        for staging in tmp_path.glob('.staging*'):
            (staging / 'probe-response.json').write_text('temporary')
        return {'exit_code': 0, 'stdout': json.dumps({'records': [{'url': 'https://example.com/item', 'title': 'record'}]})}
    monkeypatch.setattr(command_runtime, 'run_command', run)
    target = tmp_path / 'example-com'
    assert await build_skill('example.com', ['https://example.com/item'], output_dir=target, builder_model=Model()) == target
    assert sorted(p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()) == ['SKILL.md', 'scripts/search.py']
    assert not list(tmp_path.glob('.staging*'))


@pytest.mark.asyncio
async def test_failed_build_preserves_existing_package(tmp_path, monkeypatch):
    target = tmp_path / 'example-com'
    target.mkdir()
    (target / 'SKILL.md').write_text('existing version')
    class Model:
        def bind_tools(self, tools): return self
        async def ainvoke(self, messages): return AIMessage(content='完成')
    assert await build_skill('example.com', [], output_dir=target, builder_model=Model(), max_turns=2) is None
    assert (target / 'SKILL.md').read_text() == 'existing version'
    assert not list(tmp_path.glob('.staging*'))


@pytest.mark.asyncio
async def test_builder_rejects_legacy_files_and_framework_imports(tmp_path):
    workspace = BuilderWorkspace(tmp_path / 'example-com')
    try:
        with pytest.raises(ValueError):
            await workspace.write_file('executor.py', 'pass')
        await workspace.write_file('SKILL.md', '---\nname: example-com\ndescription: 查询记录\nmetadata:\n  searchos-category: access\n  host: example.com\n---\n说明')
        await workspace.write_file('scripts/search.py', 'import searchos\n')
        assert not _portable_skill_is_complete(workspace.output_dir, 'example-com')
    finally:
        workspace.close()


@pytest.mark.asyncio
async def test_generated_package_runs_through_runtime_and_outside_searchos(tmp_path):
    import subprocess
    import sys
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from searchos.skills.packaging import export_package

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            payload = json.dumps({'records': [{'title': 'Local service record', 'source_url': f'http://127.0.0.1:{self.server.server_port}/record'}]}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(payload)
        def log_message(self, *args): pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{server.server_port}/record'
    script = '''import argparse, json, urllib.request
parser = argparse.ArgumentParser()
parser.add_argument('--url', required=True)
args = parser.parse_args()
with urllib.request.urlopen(args.url, timeout=5) as response:
    print(json.dumps(json.load(response)))
'''
    class Model:
        count = 0
        def bind_tools(self, tools): return self
        async def ainvoke(self, messages):
            self.count += 1
            if self.count > 1: return AIMessage(content='完成')
            return AIMessage(content='', tool_calls=[
                {'id': '1', 'name': 'write_file', 'args': {'path': 'SKILL.md', 'content': '---\nname: example-com\ndescription: 查询指定来源记录\nmetadata:\n  searchos-category: access\n  host: example.com\n---\n执行 python scripts/search.py --url URL，结果为 JSON。'}},
                {'id': '2', 'name': 'write_file', 'args': {'path': 'scripts/search.py', 'content': script}},
                {'id': '3', 'name': 'register_example', 'args': {'argv': ['python', 'scripts/search.py', '--url', url], 'output': '', 'records_key': 'records'}},
            ])
    try:
        target = tmp_path / 'library/example-com'
        assert await build_skill('example.com', [url], output_dir=target, builder_model=Model()) == target
        exported = export_package(target, tmp_path / 'export/example-com')
        result = subprocess.run([sys.executable, '-I', str(exported / 'scripts/search.py'), '--url', url], cwd=tmp_path, capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)['records'][0]['title'] == 'Local service record'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.asyncio
async def test_access_validation_reports_misplaced_host_metadata(tmp_path):
    workspace = BuilderWorkspace(tmp_path / 'example-com')
    try:
        await workspace.write_file('SKILL.md', '---\nname: example-com\ndescription: 查询记录\nsearchos-category: access\nhost: example.com\n---\n说明')
        await workspace.write_file('scripts/search.py', 'print(1)')
        report = await workspace.validate()
        assert report['stage'] == 'package'
        assert 'metadata.searchos-category' in report['error']
    finally:
        workspace.close()
