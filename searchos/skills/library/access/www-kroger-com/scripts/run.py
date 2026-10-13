"""独立技能 CLI；只使用标准库，检索依赖在运行时加载。"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import importlib.util
import inspect
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent


def boolean(value):
    if value.lower() in ('true', '1', 'yes'):
        return True
    if value.lower() in ('false', '0', 'no'):
        return False
    raise argparse.ArgumentTypeError('expected true or false')


def validate(params, schema):
    unknown = set(params) - set(schema)
    if unknown:
        raise ValueError('unknown parameters: ' + ', '.join(sorted(unknown)))
    types = {'string': str, 'integer': int, 'number': (int, float),
             'boolean': bool, 'array': list, 'object': dict, 'null': type(None)}
    for key, spec in schema.items():
        if key not in params:
            if spec.get('required'):
                raise ValueError('missing required parameter: ' + key)
            continue  # Unspecified values retain the source implementation's defaults.
        value, kind = params[key], spec.get('type', 'string')
        kinds = kind if isinstance(kind, list) else [kind]
        if not any(k not in types or (isinstance(value, types[k]) and
                not (k in ('integer', 'number') and isinstance(value, bool))) for k in kinds):
            raise ValueError(f'{key}: expected {kind}')
        if 'enum' in spec and value not in spec['enum']:
            raise ValueError(f'{key}: expected one of {spec["enum"]}')


async def invoke(params):
    spec = importlib.util.spec_from_file_location('skill_source', ROOT / 'scripts/source.py')
    module = importlib.util.module_from_spec(spec)
    # Register for decorators such as dataclass; imports do not require the host.
    sys.modules[spec.name] = module
    with contextlib.redirect_stdout(sys.stderr):
        spec.loader.exec_module(module)
        result = module.execute(params, None)
        if inspect.isawaitable(result):
            result = await result
    if not isinstance(result, dict):
        raise ValueError('source must return a JSON object')
    return result


def main(argv=None):
    contract = json.loads((ROOT / 'references/parameters.json').read_text(encoding='utf-8'))
    schema = contract['parameters']
    parser = argparse.ArgumentParser(description=contract['description'])
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument('--params', help='JSON parameter object')
    inputs.add_argument('--params-file', help='UTF-8 JSON parameter file; - reads stdin')
    parser.add_argument('--result-file', help='write JSON to this path; otherwise stdout')
    parser.add_argument('--validate-only', action='store_true', help='validate parameters without imports or network')
    parser.add_argument('--check-dependencies', action='store_true', help='check Python modules without executing the source')
    reserved = {'params', 'params-file', 'result-file', 'validate-only', 'check-dependencies', 'help'}
    for key, spec in schema.items():
        option = key.replace('_', '-')
        option = 'arg-' + option if option in reserved else option
        kind = spec.get('type', 'string')
        if isinstance(kind, list):
            kind = next((item for item in kind if item != 'null'), 'string')
        converter = {'integer': int, 'number': float, 'boolean': boolean,
                     'array': json.loads, 'object': json.loads}.get(kind, str)
        parser.add_argument('--' + option, dest='param:' + key, default=argparse.SUPPRESS,
                            type=converter, help=spec.get('description', '').replace('%', '%%'))
    args = parser.parse_args(argv)
    if args.check_dependencies:
        missing = [module for module in contract['imports'] if importlib.util.find_spec(module) is None]
        print(json.dumps({'missing_modules': missing, 'requirements': contract['requirements']}, ensure_ascii=False))
        return 1 if missing else 0
    try:
        raw = args.params or '{}'
        if args.params_file:
            raw = sys.stdin.read() if args.params_file == '-' else Path(args.params_file).read_text(encoding='utf-8')
        params = json.loads(raw)
        if not isinstance(params, dict):
            raise ValueError('params must be a JSON object')
        params.update({key[6:]: value for key, value in vars(args).items() if key.startswith('param:')})
        validate(params, schema)
        if args.validate_only:
            print(json.dumps({'valid': True, 'parameters': params}, ensure_ascii=False))
            return 0
        result = asyncio.run(invoke(params))
        payload = json.dumps(result, ensure_ascii=False, allow_nan=False)
        if args.result_file:
            output = Path(args.result_file)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(payload + '\n', encoding='utf-8')
        else:
            print(payload)
        failed = bool(result.get('error')) or result.get('success') is False or result.get('status') in ('error', 'failed', 'failure')
        if failed:
            print(str(result.get('error') or 'source returned failure'), file=sys.stderr)
        return 1 if failed else 0
    except Exception as exc:
        print(f'{type(exc).__name__}: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
