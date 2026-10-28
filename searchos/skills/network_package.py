"""把验收线路写入 Portable Skill 的普通 Python 代码。"""
from __future__ import annotations

import ast
import json
from pathlib import Path
import re

_MODES = {'direct', 'proxy', 'inherit'}
_TEMPLATE = Path(__file__).with_name('network_template.py')


def _name(node, aliases):
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        return _name(node.value, aliases) + '.' + node.attr
    return ''


def _rewrite(source: str, stem: str) -> tuple[str, set[str]]:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    def position(line, column):
        return offsets[line - 1] + len(lines[line - 1].encode('utf-8')[:column].decode('utf-8'))
    def span(node):
        return position(node.lineno, node.col_offset), position(node.end_lineno, node.end_col_offset)
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                aliases[item.asname or item.name.split('.')[0]] = item.name if item.asname else item.name.split('.')[0]
        elif isinstance(node, ast.ImportFrom):
            for item in node.names:
                aliases[item.asname or item.name] = (node.module or '') + '.' + item.name
    edits = []
    clients = set()
    thread_context = False
    replacements = {
        'aiohttp.ClientSession': ('aiohttp_session', 'aiohttp'),
        'httpx.Client': ('httpx_client', 'httpx'),
        'httpx.AsyncClient': ('httpx_async_client', 'httpx'),
        'urllib.request.urlopen': ('urllib_urlopen', 'urllib'),
        'urllib.request.build_opener': ('urllib_build_opener', 'urllib'),
    }
    thread_executors = set()
    for node in ast.walk(tree):
        bindings = [(item.optional_vars, item.context_expr) for item in node.items] if isinstance(node, ast.With) else []
        if isinstance(node, ast.Assign):
            bindings += [(target, node.value) for target in node.targets]
        for target, value in bindings:
            if isinstance(target, ast.Name) and isinstance(value, ast.Call) and _name(value.func, aliases) == 'concurrent.futures.ThreadPoolExecutor':
                thread_executors.add(target.id)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _name(node.func, aliases)
        if name in replacements:
            factory, client = replacements[name]
            start, end = span(node.func)
            edits.append((start, end, '_skill_network.' + factory))
            clients.add(client)
        elif isinstance(node.func, ast.Attribute) and node.func.attr in ('launch', 'launch_persistent_context') and _name(node.func.value, aliases).endswith(('.chromium', '.firefox', '.webkit')):
            start, end = span(node.func)
            receiver_start, receiver_end = span(node.func.value)
            factory = 'browser_' + node.func.attr
            edits.append((start, end, '_skill_network.' + factory))
            opening = source.index('(', end, span(node)[1]) + 1
            edits.append((opening, opening, source[receiver_start:receiver_end] + (', ' if node.args or node.keywords else '')))
            clients.add('playwright')
        elif isinstance(node.func, ast.Attribute) and node.func.attr in ('new_context', 'new_page') and not name.startswith('_skill_network.'):
            start, end = span(node.func)
            receiver_start, receiver_end = span(node.func.value)
            edits.append((start, end, '_skill_network.browser_' + node.func.attr))
            opening = source.index('(', end, span(node)[1]) + 1
            edits.append((opening, opening, source[receiver_start:receiver_end] + (', ' if node.args or node.keywords else '')))
        elif name.startswith(('requests.', 'curl_cffi.requests.')) and name.rsplit('.', 1)[-1] in ('get', 'post', 'put', 'delete', 'head', 'options', 'patch', 'request', 'Session'):
            start, end = span(node.func)
            factory = 'requests_session' if name.endswith('.Session') else 'requests_call'
            edits.append((start, end, '_skill_network.' + factory))
            opening = source.index('(', end, span(node)[1]) + 1
            edits.append((opening, opening, source[start:end] + (', ' if node.args or node.keywords else '')))
            clients.add('curl_cffi' if name.startswith('curl_cffi') else 'requests')
        elif name in ('os.environ.get',) and node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value == 'SEARCHOS_PROXY_MODE':
            start, end = span(node)
            edits.append((start, end, '_skill_network.mode()'))
        elif (isinstance(node.func, ast.Attribute) and node.func.attr == 'run_in_executor' and len(node.args) >= 2
              and (isinstance(node.args[0], ast.Constant) and node.args[0].value is None
                   or isinstance(node.args[0], ast.Name) and node.args[0].id in thread_executors)):
            if ast.unparse(node.args[1]) != '_skill_contextvars.copy_context().run':
                start, _ = span(node.args[1])
                edits.append((start, start, '_skill_contextvars.copy_context().run, '))
                thread_context = True
    handlers = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'HANDLERS' for target in node.targets) and isinstance(node.value, ast.Dict):
            for key, value in zip(node.value.keys, node.value.values):
                if isinstance(key, ast.Constant) and isinstance(key.value, str) and isinstance(value, ast.Name):
                    handlers[value.id] = key.value
    entrypoints = {'execute', 'execute_async', 'main'}
    native = bool(clients) or '_skill_network.' in source or bool(handlers) or any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in entrypoints for node in tree.body)
    if not native:
        return source, clients
    if thread_context and not any(isinstance(node, ast.Import) and any(item.name == 'contextvars' and item.asname == '_skill_contextvars' for item in node.names) for node in tree.body):
        at = next((offsets[node.lineno - 1] for node in tree.body if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)) and not (isinstance(node, ast.ImportFrom) and node.module == '__future__')), len(source))
        edits.append((at, at, 'import contextvars as _skill_contextvars\n'))
    # Isolated Python omits the script directory from sys.path.
    bootstrap = "import sys as _skill_sys, os as _skill_os\n_skill_sys.path.insert(0, _skill_os.path.dirname(_skill_os.path.abspath(__file__)))\n"
    if '_skill_sys.path.insert(0,' not in source:
        existing_import = next((node for node in tree.body if isinstance(node, ast.Import) and any(item.asname == '_skill_network' and item.name == '_network' for item in node.names)), None)
        if existing_import is not None:
            at = offsets[existing_import.lineno - 1]
            edits.append((at, at, bootstrap))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (node.name in entrypoints or node.name in handlers):
            if any('_skill_network.entrypoint' in ast.unparse(item) for item in node.decorator_list):
                continue
            start = offsets[node.lineno - 1]
            if node.name in handlers:
                decorator = f'@_skill_network.entrypoint(capability_id={handlers[node.name]!r})'
            else:
                decorator = '@_skill_network.entrypoint' if node.name != 'main' else f'@_skill_network.entrypoint(capability_id={stem!r}, cli=True)'
            edits.append((start, start, decorator + '\n'))
    if not any(isinstance(node, ast.Import) and any(item.asname == '_skill_network' and item.name == '_network' for item in node.names) for node in tree.body):
        insert_line = 0
        for index, node in enumerate(tree.body):
            if index == 0 and isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                insert_line = node.end_lineno
            elif isinstance(node, ast.ImportFrom) and node.module == '__future__':
                insert_line = node.end_lineno
            else:
                break
        # Keep a shebang and encoding declaration before imports.
        if not insert_line:
            while insert_line < len(lines) and lines[insert_line].startswith('#'):
                insert_line += 1
        at = offsets[insert_line]
        edits.append((at, at, bootstrap + 'import _network as _skill_network\n'))
    for start, end, replacement in sorted(edits, key=lambda item: (item[0], item[1]), reverse=True):
        source = source[:start] + replacement + source[end:]
    ast.parse(source)
    return source, clients


def _example_aliases(examples, selected):
    aliases = {}
    scripts = {}
    for example in examples:
        if not isinstance(example, dict):
            continue
        capability = example.get('capability_id') or 'package'
        argv = example.get('argv') or []
        params = example.get('params') or example.get('parameters') or {}
        for index, value in enumerate(argv):
            if value in ('--params', '--input') and index + 1 < len(argv):
                try:
                    params = json.loads(argv[index + 1])
                except (ValueError, TypeError):
                    pass
            if capability in selected and value in ('--function', '--method') and index + 1 < len(argv):
                aliases[argv[index + 1]] = capability
            if isinstance(value, str) and value.endswith('.py'):
                scripts.setdefault(Path(value).stem, set()).add(capability)
        if capability in selected and isinstance(params, dict):
            for key in ('function', 'method'):
                if params.get(key):
                    aliases[str(params[key])] = capability
    for stem, capabilities in scripts.items():
        if len(capabilities) == 1 and capabilities <= selected:
            aliases[stem] = next(iter(capabilities))
    return aliases


def bind_network_defaults(package_dir, examples, proxy_mode, capability_ids=None) -> dict:
    """离线固化线路，并返回更改文件供版本及验收跟踪。"""
    if proxy_mode not in _MODES:
        raise ValueError('proxy_mode must be direct, proxy, or inherit')
    package = Path(package_dir)
    scripts = package / 'scripts'
    if not scripts.is_dir():
        raise ValueError('package must contain scripts/')
    selected = set(capability_ids) if capability_ids is not None else {item.get('capability_id') or 'package' for item in examples if isinstance(item, dict)}
    selected = selected or {'package'}
    config_path = scripts / 'network.json'
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding='utf-8'))
    else:
        config = {'version': 1, 'default': 'inherit', 'functions': {}}
    config.setdefault('functions', {})
    if 'package' in selected:
        config['default'] = proxy_mode
    for capability in selected - {'package'}:
        config['functions'][capability] = proxy_mode
    aliases = _example_aliases(examples, selected)
    if aliases:
        config.setdefault('aliases', {}).update(aliases)
    writes = {}
    all_clients = set()
    for path in sorted(scripts.rglob('*.py')):
        if path.name == '_network.py':
            continue
        original = path.read_text(encoding='utf-8')
        transformed, clients = _rewrite(original, path.stem)
        all_clients.update(clients)
        if transformed != original:
            writes[path] = transformed
    existing = any('_skill_network.' in path.read_text(encoding='utf-8') for path in scripts.rglob('*.py') if path.name != '_network.py')
    if not all_clients and not existing and not writes:
        # Offline skills can still declare a stable default before adding I/O.
        if not any(scripts.rglob('*.py')):
            raise ValueError('package must contain a Python entry point')
    writes[scripts / '_network.py'] = _TEMPLATE.read_text(encoding='utf-8')
    writes[config_path] = json.dumps(config, ensure_ascii=False, indent=2) + '\n'
    requirements = package / 'requirements.txt'
    if 'aiohttp' in all_clients and requirements.exists():
        content = requirements.read_text(encoding='utf-8')
        updated = re.sub(r'(?m)^aiohttp(?:\s*[<>=!~].*)?\s*$', 'aiohttp>=3.12', content)
        if updated != content:
            writes[requirements] = updated
    changed = []
    for path, content in writes.items():
        if not path.exists() or path.read_text(encoding='utf-8') != content:
            path.write_text(content, encoding='utf-8')
            changed.append(str(path.relative_to(package)))
    return {'files': sorted(changed), 'capability_ids': sorted(selected), 'proxy_mode': proxy_mode,
            'network_clients': sorted(all_clients), 'config': 'scripts/network.json'}
