"""迁移包内网络默认值，并通过纯业务 CLI 逐能力核验实际来源访问。"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import time
import uuid

from searchos.skills.network_package import bind_network_defaults
from searchos.skills.runtime.command_runtime import run_command
from searchos.skills.runtime.network import proxy_environment


def _json_write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def _capabilities(schema):
    for selector in ('function', 'method'):
        if selector in schema:
            spec = schema[selector]
            names = spec.get('enum') or re.findall(
                r'^\s*-\s*([A-Za-z][A-Za-z0-9_-]*)', spec.get('description', ''), re.M)
            return selector, list(dict.fromkeys(names))
    return None, ['package']


def _bounded_params(params, schema):
    params = dict(params)
    for name, spec in schema.items():
        if name not in params and 'default' in spec:
            params[name] = spec['default']
    for name in ('limit', 'max_results', 'num_results', 'rank_limit', 'rows', 'page_size', 'per_page'):
        if isinstance(params.get(name), int) and not isinstance(params[name], bool) and params[name] > 3:
            params[name] = max(schema.get(name, {}).get('minimum', 1), 3)
    return params


def _example(capability, argv, params=None, origin='existing_documentation'):
    return {'capability_id': capability, 'argv': argv, 'params': params or {}, 'origin': origin}


def custom_examples(name):
    if name == 'api-datamuse-com':
        return [_example('query', ['python', 'scripts/query.py', '--query', 'research', '--limit', '3'])]
    if name == 'arxiv-search':
        return [_example('search', ['python', 'scripts/search.py', '--query', 'all:retrieval', '--limit', '2'])]
    if name == 'developer-mozilla-org':
        return [_example(cap, ['python', 'scripts/access.py', cap, '--input', json.dumps(params)])
                for cap, params in [('read_document', {'path': '/docs/Web/CSS/display'}),
                                    ('list_reference_index', {'section': '/docs/Web/API'})]]
    if name == 'aiweekly-co':
        return [_example('get_news_by_date', ['python', 'scripts/access.py', 'get_news_by_date',
                                            '--input', '{"date":"October 19"}'])]
    if name == 'yahoo-finance-quote':
        return [_example('quote', ['python', 'scripts/quote.py', 'AAPL']),
                _example('history', ['python', 'scripts/history.py', 'AAPL', '--days', '2'])]
    if name == 'x-com':
        return [_example('get_tweet', ['python', 'scripts/get_tweet.py', '--id', '20']),
                _example('get_user', ['python', 'scripts/get_user.py', '--username', 'NASA']),
                _example('get_tweets', ['python', 'scripts/get_tweets.py', '--ids', '20,21'])]
    return []


def build_plan(item, max_examples=1):
    """从现有参数契约与文档样例建立业务调用，缺少输入时明确保留缺口。"""
    package = Path(item['package']).resolve()
    contract = package / 'references/parameters.json'
    if not contract.is_file():
        return custom_examples(item['skill'])
    schema = json.loads(contract.read_text(encoding='utf-8'))['parameters']
    selector, capabilities = _capabilities(schema)
    documented = item.get('examples', [])
    if selector:
        capabilities = list(dict.fromkeys([*capabilities, *[
            str(params[selector]) for params in documented if params.get(selector)
        ]]))
    examples = []
    for capability in capabilities or ['package']:
        candidates = [params for params in documented
                      if not selector or params.get(selector) == capability]
        if not candidates:
            params = {selector: capability} if selector else {}
            missing = [key for key, spec in schema.items()
                       if spec.get('required') and key not in params and 'default' not in spec]
            if not missing:
                candidates = [params]
            elif missing == ['query']:
                candidates = [{**params, 'query': 'information retrieval'}]
        if not candidates:
            examples.append({'capability_id': capability, 'argv': None,
                             'reason': 'missing_documented_business_input'})
            continue
        for index, candidate in enumerate(candidates[:max_examples]):
            params = _bounded_params(candidate, schema)
            argv = ['python', 'scripts/run.py', '--params', json.dumps(params, ensure_ascii=False)]
            examples.append(_example(capability, argv, params,
                                     'existing_documentation' if candidate in documented
                                     else 'declared_defaults_or_public_search'))
            examples[-1]['input_index'] = index
    if item['skill'] == 'www-reddit-com':
        examples.append(_example('reddit_rss', ['python', 'scripts/reddit_rss.py',
                                                '--subreddit', 'python', '--limit', '2']))
    return examples


def _source_fingerprint(package):
    digest = hashlib.sha256()
    for path in sorted((package / 'scripts').rglob('*.py')):
        digest.update(path.relative_to(package).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _payload_result(value):
    """核对业务结果，保留各旧包的原始返回结构。"""
    if isinstance(value, list):
        return ('passed', '') if value else ('empty_result', 'business result is empty')
    if not isinstance(value, dict):
        return 'invalid_output', 'business CLI must return a JSON object or array'
    if value.get('error') or value.get('success') is False or value.get('status') in {
            'error', 'failed', 'failure', 'invalid_input', 'access_error', 'parse_error', 'auth_required'}:
        detail = value.get('error')
        if isinstance(detail, bool) or not detail:
            detail = value.get('message') or value.get('error_message') or value.get('warnings') or value.get('status') or 'source returned failure'
        return 'business_failure', str(detail)[:1500]
    for key in ('records', 'results', 'items', 'data', 'articles', 'posts', 'entries',
                'companies', 'billionaires', 'people', 'books', 'papers', 'products',
                'videos', 'news', 'tweets', 'users', 'quotes', 'history'):
        if key in value and isinstance(value[key], (list, dict)):
            if value[key]:
                return 'passed', ''
            return 'empty_result', f'{key} is empty'
    meaningful = {key: item for key, item in value.items()
                  if key not in {'success', 'status', 'warnings', 'error', 'count', 'total', 'url',
                                 'source', 'source_url', 'request_url', 'retrieved_at', 'query',
                                 'function', 'method', 'parameters', 'limit', 'page',
                                 'year', 'date', 'returned_count', 'total_count', 'timestamp'}}
    if any(item not in (None, '', [], {}) for item in meaningful.values()):
        return 'passed', ''
    return 'empty_result', 'no business data in result'


def _mode(package, capability):
    config = json.loads((package / 'scripts/network.json').read_text(encoding='utf-8'))
    selected = config.get('functions', {}).get(capability, config.get('default', 'inherit'))
    return selected.get('mode', 'inherit') if isinstance(selected, dict) else selected


def _prepare_package(item, examples):
    """保留已固化线路，仅为尚未配置的能力补齐默认值。"""
    package = Path(item['package']).resolve()
    direct_clients = set(item.get('network_client_kinds', [])) <= {'aiohttp', 'playwright'}
    explicit_direct = any(call.get('explicit_trust_env') in (False, 'False') for call in item.get('network_calls', []))
    initial = 'direct' if direct_clients or explicit_direct else 'inherit'
    config_path = package / 'scripts/network.json'
    all_examples = examples or [{'capability_id': 'package'}]
    if not config_path.is_file():
        return bind_network_defaults(package, all_examples, initial)
    config = json.loads(config_path.read_text(encoding='utf-8'))
    selected = {example.get('capability_id', 'package') for example in all_examples}
    missing = selected - set(config.get('functions', {})) - ({'package'} if 'default' in config else set())
    if missing:
        return bind_network_defaults(package, all_examples, initial, capability_ids=missing)
    # Refresh code without changing the stored route or the remaining functions.
    capability = sorted(selected)[0]
    return bind_network_defaults(package, all_examples, _mode(package, capability), capability_ids={capability})


def _classify(result, work, saved, expected_mode=None):
    stdout = saved / 'stdout.log'
    text = stdout.read_text(encoding='utf-8', errors='replace') if stdout.is_file() else result.get('stdout', '')
    trace = work / 'network.log'
    events = []
    if trace.is_file():
        for line in trace.read_text(encoding='utf-8', errors='replace').splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                continue
    reason = result.get('error') or result.get('stderr_tail') or result.get('stderr') or ''
    if result.get('timed_out'):
        return 'timed_out', 'business CLI exceeded its execution deadline', events, None
    if result.get('auth_required'):
        return 'authentication_required', str(reason)[:1500], events, None
    try:
        payload = json.loads(text)
    except ValueError:
        status = 'dependency_missing' if re.search(r'ModuleNotFoundError|No module named', str(reason)) else 'invalid_output'
        return status, str(reason or 'CLI did not return JSON')[-1500:], events, None
    status, business_reason = _payload_result(payload)
    if result.get('exit_code') != 0 or result.get('status') != 'completed':
        if status == 'passed':
            status = 'business_failure'
        return status, str(business_reason or reason)[-1500:], events, payload
    if status == 'passed' and not any(200 <= event.get('status', 0) < 300 for event in events):
        return 'live_access_unconfirmed', 'business output returned without a confirmed successful source response', events, payload
    if status == 'passed' and expected_mode and any(event.get('mode') != expected_mode for event in events):
        return 'network_binding_mismatch', 'source access did not use the stored function route', events, payload
    return status, business_reason, events, payload


async def migrate_and_validate(args):
    inventory = json.loads(args.inventory.read_text(encoding='utf-8'))
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    packages = [item for item in inventory['packages']
                if not args.only or item['skill'] in args.only.split(',')]
    plans = {item['skill']: build_plan(item, args.max_examples) for item in packages}
    _json_write(output / 'business-plan.json', plans)
    migrate_log = []
    for item in packages:
        package = Path(item['package']).resolve()
        backup = output / 'original-packages' / item['skill']
        if not backup.exists():
            shutil.copytree(package, backup, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        examples = plans[item['skill']]
        try:
            receipt = _prepare_package(item, examples)
            migrate_log.append({'skill': item['skill'], 'status': 'migrated', **receipt})
        except (ValueError, OSError, SyntaxError) as exc:
            migrate_log.append({'skill': item['skill'], 'status': 'migration_failed', 'reason': str(exc)})
    _json_write(output / 'migration.json', migrate_log)
    if args.migrate_only:
        print(json.dumps(dict(Counter(item['status'] for item in migrate_log))), flush=True)
        return
    ready = {item['skill'] for item in migrate_log if item['status'] == 'migrated'}
    has_proxy = any(key in proxy_environment('inherit') for key in ('http_proxy', 'https_proxy', 'all_proxy'))
    semaphore = asyncio.Semaphore(args.concurrency)
    browser_slots = asyncio.Semaphore(args.browser_concurrency)
    cases = []
    counts = Counter()
    old_cases = {}
    if args.resume and (output / 'cases.jsonl').is_file():
        for line in (output / 'cases.jsonl').read_text(encoding='utf-8').splitlines():
            try:
                old = json.loads(line)
                old_cases[(old['skill'], old['capability_id'], old.get('input_index', 0))] = old
            except (ValueError, KeyError):
                continue
    locks = {item['skill']: asyncio.Lock() for item in packages}
    started = time.monotonic()

    def record(case):
        cases.append(case)
        counts[case['status']] += 1
        with (output / 'cases.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(case, ensure_ascii=False) + '\n')
        if len(cases) % 10 == 0:
            print(json.dumps({'completed': len(cases), 'seconds': round(time.monotonic() - started),
                              'results': dict(counts)}, ensure_ascii=False), flush=True)

    async def one(item, example):
        skill = item['skill']
        package = Path(item['package']).resolve()
        capability = example['capability_id']
        base = {'skill': skill, 'capability_id': capability, 'input_index': example.get('input_index', 0),
                'argv': example.get('argv'), 'checked_at': datetime.now(timezone.utc).isoformat()}
        if skill not in ready or not example.get('argv'):
            record({**base, 'status': 'incomplete', 'reason': example.get('reason', 'package migration failed')})
            return
        is_browser = 'playwright' in item.get('network_client_kinds', [])
        async with locks[skill]:
            fingerprint = _source_fingerprint(package)
            previous = old_cases.get((skill, capability, base['input_index']))
            if (previous and previous.get('source_fingerprint') == fingerprint
                    and previous.get('mode') == _mode(package, capability)
                    and previous.get('argv') == base['argv']):
                record({**previous, 'resumed': True})
                return
            if is_browser:
                await browser_slots.acquire()
            await semaphore.acquire()
            try:
                preferred = _mode(package, capability)
                modes = list(dict.fromkeys([preferred, 'direct', *(['proxy'] if has_proxy else [])]))
                attempts = []
                final = None
                for index, mode in enumerate(modes):
                    bind_network_defaults(package, [example], mode, capability_ids={capability})
                    identity = hashlib.sha256((skill + '\0' + capability + '\0' + str(base['input_index'])).encode()).hexdigest()[:20]
                    run_root = output / 'runs' / identity / uuid.uuid4().hex / str(index)
                    work = run_root / 'work'
                    records = run_root / 'executions'
                    result = await run_command(package, example['argv'], work_dir=work, execution_dir=records,
                                               timeout_s=args.browser_timeout if is_browser else args.timeout,
                                               network=True, network_audit=True)
                    saved = records / result.get('execution_id', 'missing')
                    status, reason, events, payload = _classify(result, work, saved, mode)
                    attempt = {'mode': mode, 'status': status, 'reason': reason,
                               'execution_id': result.get('execution_id'), 'backend': result.get('backend'),
                               'exit_code': result.get('exit_code'), 'network_events': events,
                               'record': str(saved / 'record.json')}
                    attempts.append(attempt)
                    final = {**base, 'status': status, 'reason': reason, 'mode': mode,
                             'source_fingerprint': _source_fingerprint(package), 'attempts': attempts}
                    if payload is not None:
                        _json_write(run_root / 'business-result.json', payload)
                    if status == 'passed' or status in {'dependency_missing', 'authentication_required'}:
                        break
                    if not events and status == 'business_failure' and re.search(
                            r'missing|required|invalid|unknown function|unsupported function', reason, re.I):
                        final['status'] = 'incomplete'
                        final['reason'] = 'documented input was rejected: ' + reason
                        break
                if final['status'] != 'passed':
                    bind_network_defaults(package, [example], preferred, capability_ids={capability})
                    final['mode'] = preferred
                record(final)
            except asyncio.CancelledError:
                bind_network_defaults(package, [example], preferred, capability_ids={capability})
                raise
            except Exception as exc:
                bind_network_defaults(package, [example], preferred, capability_ids={capability})
                record({**base, 'status': 'validation_error', 'mode': preferred,
                        'reason': f'{type(exc).__name__}: {exc}',
                        'source_fingerprint': _source_fingerprint(package), 'attempts': attempts})
            finally:
                semaphore.release()
                if is_browser:
                    browser_slots.release()

    await asyncio.gather(*(one(item, example) for item in packages
                           for example in plans[item['skill']]))
    by_skill = {}
    for item in packages:
        selected = [case for case in cases if case['skill'] == item['skill']]
        by_skill[item['skill']] = {'package': item['package'], 'cases': len(selected),
                                  'results': dict(Counter(case['status'] for case in selected))}
    summary = {'checked_at': datetime.now(timezone.utc).isoformat(), 'packages': len(packages),
               'capability_cases': len(cases), 'results': dict(counts), 'by_skill': by_skill,
               'scope': 'default business CLI, actual source-response trace and structured nonempty output; independent semantic review is outside this network check'}
    _json_write(output / 'summary.json', summary)
    print(json.dumps({key: value for key, value in summary.items() if key != 'by_skill'}, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--only', default='')
    parser.add_argument('--concurrency', type=int, default=10)
    parser.add_argument('--browser-concurrency', type=int, default=2)
    parser.add_argument('--timeout', type=float, default=15)
    parser.add_argument('--browser-timeout', type=float, default=25)
    parser.add_argument('--max-examples', type=int, default=1)
    parser.add_argument('--migrate-only', action='store_true')
    parser.add_argument('--resume', action='store_true')
    asyncio.run(migrate_and_validate(parser.parse_args()))


if __name__ == '__main__':
    main()
