"""将旧库原位转换为独立技能包；先验证全部候选，再逐包原子替换。"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile

import yaml

from searchos.skills.core.schema import parse_skill_file
from searchos.skills.packaging import validate_package

DISTRIBUTIONS = {'bs4': 'beautifulsoup4', 'PIL': 'Pillow', 'dateutil': 'python-dateutil'}
TEMPLATE = Path(__file__).with_name('migration_templates') / 'run.py'


def portable_name(name):
    value = re.sub('[^a-z0-9]+', '-', name.lower()).strip('-')
    if len(value) > 64:
        value = value[:53].rstrip('-') + '-' + hashlib.sha256(name.encode()).hexdigest()[:10]
    if not value:
        raise ValueError(f'invalid name: {name}')
    return value


def dependencies(source):
    modules = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split('.')[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split('.')[0])
    external = sorted(modules - sys.stdlib_module_names - {'__future__'})
    if 'searchos' in external:
        raise ValueError('remaining host import')
    return external, [DISTRIBUTIONS.get(name, name) for name in external]


def plan(library):
    candidates = []
    targets = set()
    for entry in sorted(library.rglob('*')):
        if entry.name != 'skill.md' or any(part.startswith(('_', '.')) for part in entry.relative_to(library).parts):
            continue
        skill = parse_skill_file(entry)
        name = portable_name(skill.meta.name)
        destination = entry.parent.with_name(name)
        if destination in targets or (destination != entry.parent and destination.exists()):
            raise ValueError(f'destination collision: {destination}')
        targets.add(destination)
        candidates.append((entry.parent, destination, skill))
    return candidates


def migrate(library: Path, aliases_path: Path):
    library = library.resolve()
    candidates = plan(library)
    aliases = json.loads(aliases_path.read_text()) if aliases_path.exists() else {}
    for source, destination, skill in candidates:
        for old in {source.name, skill.meta.name}:
            if old != destination.name:
                if old in aliases and aliases[old] != destination.name:
                    raise ValueError('alias collision: ' + old)
                aliases[old] = destination.name
    report = []
    # Stage outside the library so no incomplete package becomes discoverable.
    with tempfile.TemporaryDirectory(prefix='skill-migration-', dir=library.parent) as tmp:
        staged = []
        for index, (source, destination, skill) in enumerate(candidates):
            package = Path(tmp) / str(index) / destination.name
            shutil.copytree(source, package, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            (package / 'skill.md').unlink()
            name = destination.name
            category = source.relative_to(library).parts[0]
            metadata = {'searchos-category': category, 'searchos-aliases': source.name,
                        'searchos-config': json.dumps(skill.meta.model_dump(mode='json', exclude={'name', 'description', 'has_executor', 'metadata'}), ensure_ascii=False)}
            front = {'name': name, 'description': (skill.meta.description or skill.meta.trigger or name)[:1024], 'metadata': metadata}
            if (package / 'executor.py').exists():
                manifest_path = package / 'manifest.yaml'
                manifest = yaml.safe_load(manifest_path.read_text()) if manifest_path.exists() else {}
                manifest = manifest or {}
                params = manifest.get('params_schema', {})
                for spec in params.values():
                    if 'description' in spec:
                        spec['description'] = spec['description'].replace('skill.md', 'references/source-guide.md')
                if not params:
                    raise ValueError(f'missing parameter schema: {source}')
                code = (package / 'executor.py').read_text()
                code = code.replace('from searchos.skills.core.contract import SkillContext', 'from typing import Any as SkillContext')
                imports, requirements = dependencies(code)
                scripts, refs = package / 'scripts', package / 'references'
                scripts.mkdir(exist_ok=True); refs.mkdir(exist_ok=True)
                (scripts / 'source.py').write_text(code)
                shutil.copyfile(TEMPLATE, scripts / 'run.py')
                (package / 'executor.py').unlink()
                manifest_path.unlink(missing_ok=True)
                (refs / 'parameters.json').write_text(json.dumps({'description': front['description'], 'parameters': params,
                    'imports': imports, 'requirements': requirements}, ensure_ascii=False, indent=2) + '\n')
                (refs / 'source-guide.md').write_text('# 来源操作说明\n\n此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。\n\n' + skill.body + '\n')
                (package / 'requirements.txt').write_text('\n'.join(requirements) + ('\n' if requirements else ''))
                host = manifest.get('host')
                if not host and '_' in source.name and category == 'access' and len(source.relative_to(library).parts) == 2:
                    hosts = re.findall(r'https?://([A-Za-z0-9.-]+)', code)
                    host = next((value for value in hosts if value.replace('.', '_').replace('-', '_') == source.name), None)
                if host:metadata['host'] = str(host)
                front['compatibility'] = 'Python 3.10+；依赖见 requirements.txt；检索需要网络。' + (' 浏览器功能还需安装 Playwright Chromium。' if 'playwright' in imports else '')
                body = f'''# {name}

{front['description']}

## 调用

先定位本技能目录。脚本路径相对技能目录，输出路径相对调用者当前工作目录。脚本独立运行，不需要宿主框架。

```bash
python /path/to/{name}/scripts/run.py --help
python /path/to/{name}/scripts/run.py --params-file /path/to/parameters.json --result-file /path/to/result.json
```

参数可以用独立命令行选项（下划线转连字符）、`--params` JSON 或 `--params-file` 文件传入；文件名 `-` 表示读取 stdin。独立选项覆盖 JSON 同名值。以 [参数说明](references/parameters.json) 为准；缺省参数保留来源实现的默认行为。运行 `--validate-only` 可只校验参数，`--check-dependencies` 可检查 Python 依赖，两者均不执行检索。

阅读 [来源操作说明](references/source-guide.md) 选择功能、查询、分页和结束条件。原文中的函数调用仅描述参数语义；使用本页 CLI 执行。

## 环境与结果

依赖通过 `python -m pip install -r /path/to/{name}/requirements.txt` 安装，由调用者管理环境。''' + ('浏览器功能另需 `python -m playwright install chromium`。' if 'playwright' in imports else '') + '''

`--result-file` 保存完整 JSON；省略时输出到 stdout，诊断写 stderr。参数错误、依赖缺失、异常及来源声明失败使用非零退出码；空数组表示本次无命中，不能推断来源不存在相关记录。源码沿用原检索逻辑，公开接口和页面变化仍需实际核验。

结果保留来源返回的字段与链接，不补写虚构原文。缺少可核验正文时，继续读取结果中的原始 URL；普通结构化结果不自动成为来源证据。需要翻页时按来源游标继续调用。
'''
                kind = 'access-cli'
            else:
                front['compatibility'] = '方法型技能；使用当前宿主已有的搜索、阅读和记录能力。'
                body = '# 使用边界\n\n下文给出研究方法。提到 schema、任务派发或证据工具时，仅在宿主提供对应能力时调用；其他环境用表格、任务清单和附来源的笔记表达相同状态，不假定专有工具存在。具体方法和约束如下。\n\n' + skill.body
                kind = 'instructions'
            for old, new in sorted(aliases.items(), key=lambda x: -len(x[0])):
                body = re.sub(r'(?<![\w-])' + re.escape(old) + r'(?![\w-])', new, body)
            (package / 'SKILL.md').write_text('---\n' + yaml.safe_dump(front, allow_unicode=True, sort_keys=False) + '---\n\n' + body + '\n')
            validate_package(package)
            for file in package.rglob('*.py'):compile(file.read_text(), str(file), 'exec')
            staged.append((source, destination, package))
            report.append({'old': str(source.relative_to(library)), 'new': str(destination.relative_to(library)), 'kind': kind})
        committed = []
        try:
            for index, (source, destination, package) in enumerate(staged):
                backup = Path(tmp) / f'backup-{index}'
                source.rename(backup)
                try:
                    package.rename(destination)
                except BaseException:
                    backup.rename(source)
                    raise
                committed.append((source, destination, backup))
            temporary_aliases = aliases_path.with_suffix('.tmp')
            temporary_aliases.write_text(json.dumps(aliases, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
            temporary_aliases.replace(aliases_path)
        except BaseException:
            for source, destination, backup in reversed(committed):
                shutil.rmtree(destination)
                backup.rename(source)
            raise
    return report


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('library', type=Path)
    p.add_argument('--aliases', required=True, type=Path)
    p.add_argument('--report', required=True, type=Path)
    a = p.parse_args()
    report = migrate(a.library, a.aliases)
    a.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'converted': len(report)}))
