"""能力验收进度：函数内容、复验范围、原失败输入和结果复用。"""
from __future__ import annotations

import ast
import hashlib
import json
import textwrap
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from searchos.skills.pipeline.access.session import validate_repair_budget
from searchos.skills.pipeline.access.validation.checks import (
    _summarize_cases,
    validate_access_preflight,
)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def scan_functions(root, files, *, clean=lambda value: value):
    """索引函数、异步函数、方法和嵌套函数；位置变化保留内容指纹。"""
    functions, shared, errors, class_frames = {}, {}, [], []
    for relative in sorted(files):
        data = (Path(root) / relative).read_bytes()
        if Path(relative).suffix != '.py':
            shared[relative] = hashlib.sha256(data).hexdigest()
            continue
        try:
            source = data.decode('utf-8-sig')
            tree = ast.parse(source)
        except (SyntaxError, UnicodeError) as exc:
            errors.append({'path': relative, 'error': type(exc).__name__})
            shared[relative] = hashlib.sha256(data).hexdigest()
            continue
        lines = source.splitlines(keepends=True)
        # read_file 使用通用换行、保留 BOM，并按脱敏后的 Unicode 字符计数。
        readable = data.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n')
        readable_lines = readable.splitlines(keepends=True)

        class Collector(ast.NodeVisitor):
            scope = []

            def visit_ClassDef(self, node):
                for line in {node.lineno, *(item.lineno for item in node.decorator_list)}:
                    class_frames.append({'path': relative, 'lineno': line, 'name': node.name})
                self.scope.append(node.name)
                self.generic_visit(node)
                self.scope.pop()

            def visit_FunctionDef(self, node):
                qualified = '.'.join([*self.scope, node.name])
                identifier = f'{relative}::{qualified}'
                suffix = 2
                while identifier in functions:
                    identifier = f'{relative}::{qualified}#{suffix}'
                    suffix += 1
                start = min([node.lineno, *(item.lineno for item in node.decorator_list)])
                content = textwrap.dedent(''.join(lines[start - 1:node.end_lineno]))
                offset = len(clean(''.join(readable_lines[:start - 1])))
                end_offset = len(clean(''.join(readable_lines[:node.end_lineno])))
                functions[identifier] = {'path': relative, 'name': node.name, 'qualname': qualified,
                    'lineno': start, 'end_lineno': node.end_lineno, 'source': content,
                    'read_file': {'path': relative, 'offset': offset, 'limit': min(16000, max(1, end_offset - offset))},
                    'end_offset': end_offset,
                    'sha256': hashlib.sha256(content.encode()).hexdigest(),
                    'symbols': sorted({item.id for item in ast.walk(node) if isinstance(item, ast.Name)}
                        | {item.attr for item in ast.walk(node) if isinstance(item, ast.Attribute)})}
                self.scope.append(node.name)
                self.generic_visit(node)
                self.scope.pop()

            visit_AsyncFunctionDef = visit_FunctionDef

        Collector().visit(tree)

        class Shared(ast.NodeTransformer):
            def visit_FunctionDef(self, node):
                # 导入、全局赋值、类定义和分发路由仍参与共享版本。
                return ast.Expr(value=ast.Constant(value='function:' + node.name))

            visit_AsyncFunctionDef = visit_FunctionDef

        shared[relative] = digest(ast.dump(Shared().visit(tree), include_attributes=False))
    return {'function_count': len(functions), 'functions': functions,
            'shared_fingerprint': digest(shared), 'errors': errors, 'class_frames': class_frames}


def index_metadata(index):
    return {**index, 'functions': {key: {name: value for name, value in item.items() if name != 'source'}
                                 for key, item in index['functions'].items()}}


def function_bindings(index, cases, retained=None):
    """以真实调用为起点，纳入函数正文引用的包内函数，覆盖未执行分支。"""
    functions = index['functions']
    bindings = {}
    for case in cases:
        cap = case.get('capability_id', 'package')
        trace = case.get('function_trace') or case.get('execution', {}).get('function_trace', {})
        if trace.get('trace_file'):
            try:
                path = Path(trace['trace_file'])
                if path.is_symlink() or path.stat().st_size > 10_000_000:
                    raise ValueError('invalid function trace')
                trace = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError, TypeError):
                trace = {}
        item = bindings.setdefault(cap, {'complete': True, 'function_ids': [], 'entry_function_ids': []})
        if not trace.get('complete'):
            item['complete'] = False
        for call in trace.get('calls', []):
            if call.get('name') in {'<module>', '<listcomp>', '<dictcomp>', '<setcomp>', '<genexpr>', '<lambda>'}:
                continue
            if any(all(call.get(key) == frame[key] for key in ('path', 'lineno', 'name'))
                   for frame in index.get('class_frames', [])):
                continue
            matches = [key for key, function in functions.items()
                       if function['path'] == call.get('path')
                       and function['lineno'] == call.get('lineno')]
            if not matches:
                item['complete'] = False
            item['function_ids'].extend(matches)
            if call.get('entry_root'):
                item['entry_function_ids'].extend(matches)
    bindings.update(deepcopy(retained or {}))
    owners = {}
    for cap, item in bindings.items():
        item['observed_function_ids'] = sorted(set(item.get('observed_function_ids', item['function_ids'])))
        for key in item['observed_function_ids']:
            owners.setdefault(key, set()).add(cap)
    names = {}
    for key, item in functions.items():
        names.setdefault(item['name'], []).append(key)
    for cap, item in bindings.items():
        selected, pending = set(), list(item['function_ids'])
        while pending:
            key = pending.pop()
            if key in selected:
                continue
            selected.add(key)
            symbols = functions[key]['symbols']
            if {'eval', 'exec', 'getattr', 'globals', '__import__'}.intersection(symbols):
                pending.extend(set(functions) - selected)
            else:
                # 共用 CLI 分发函数按真实调用区分业务分支；已由其他能力执行的分支留给其使用者。
                dispatcher = key in item.get('entry_function_ids', []) and len(owners.get(key, [])) > 1
                pending.extend(ref for symbol in symbols for ref in names.get(symbol, [])
                    if ref not in selected and not (dispatcher and owners.get(ref) and cap not in owners[ref]))
        item['function_ids'] = sorted(selected)
        item['complete'] &= bool(selected) and not index['errors']
    return bindings


def contracts(capabilities, examples, plan, package_contract):
    shared = {key: value for key, value in (plan or {}).items() if key != 'capabilities'}
    return {cap: digest({'package': package_contract, 'plan': shared,
        'capability': [item for item in (plan or {}).get('capabilities', []) if item['id'] == cap],
        'examples': [item for item in examples if item.get('capability_id', 'package') == cap]})
        for cap in capabilities}


def validation_scope(index, current_contracts, previous):
    before = previous.get('function_index', {})
    old_functions, functions = before.get('functions', {}), index['functions']
    changed = sorted(key for key in set(old_functions) | set(functions)
                     if old_functions.get(key, {}).get('sha256') != functions.get(key, {}).get('sha256'))
    bindings = previous.get('function_bindings', {})
    known = {key for item in bindings.values() for key in item.get('function_ids', [])}
    shared_changed = (before.get('shared_fingerprint') != index['shared_fingerprint']
                      or bool(set(changed) - known) or bool(index['errors']))
    targets, reused, reasons = [], [], {}
    for cap, contract in current_contracts.items():
        item = previous.get('capability_results', {}).get(cap, {})
        binding = bindings.get(cap, {})
        if item.get('status') != 'available':
            reason = 'not_passed'
        elif any(command.get('capability_id') == cap for command in previous.get('regression_commands', [])):
            reason = 'pending_regressions'
        elif previous.get('cancelled') or shared_changed:
            reason = 'shared_content_changed'
        elif previous.get('function_contracts', {}).get(cap) != contract:
            reason = 'contract_changed'
        elif not binding.get('complete'):
            reason = 'function_evidence_missing'
        elif set(changed).intersection(binding.get('function_ids', [])):
            reason = 'function_content_changed'
        else:
            reused.append(cap)
            continue
        targets.append(cap)
        reasons[cap] = reason
    return {'capability_ids': targets, 'reused_capability_ids': reused,
            'function_count': index['function_count'], 'changed_function_ids': changed,
            'pending_function_ids': sorted({key for cap in targets
                for key in bindings.get(cap, {}).get('function_ids', [])} | set(changed)),
            'shared_content_changed': shared_changed, 'reasons': reasons}


def merge_reused(report, previous, reused):
    """合并原始证据，保留旧执行的候选版本和会话身份。"""
    result = deepcopy(report)
    capabilities = result.setdefault('capability_results', {})
    cases = result.setdefault('case_results', [])
    provenance = {}
    for cap in reused:
        capabilities[cap] = deepcopy(previous['capability_results'][cap])
        provenance[cap] = deepcopy(previous.get('reused_from', {}).get(cap) or {
            'candidate_version': previous.get('candidate_version', previous.get('candidate_fingerprint')),
            'validation_session': previous.get('validation_session')})
        cases.extend(deepcopy(case) for case in previous.get('case_results', [])
                     if case.get('capability_id', 'package') == cap)
    for position, case in enumerate(cases):
        case['example'] = position
    for cap, item in capabilities.items():
        item['case_indexes'] = [position for position, case in enumerate(cases)
                                if case.get('capability_id', 'package') == cap]
    result['reused_from'] = provenance
    result['valid'] = bool(result.get('package_valid') and capabilities) and all(
        item.get('status') == 'available' for item in capabilities.values())
    if result['valid']:
        result.update(stage='complete', report_complete=True)
        result.pop('error', None)
    return result


def normalized(argv, *, route=False):
    values = list(argv)
    if values and values[0] in {'python', 'python3'}:
        values[0] = 'python'
    for index, value in enumerate(argv[:-1]):
        if value == '--input':
            try:
                payload = json.loads(argv[index + 1])
                values[index + 1] = ('<business-input>' if route else
                    json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False))
            except (ValueError, TypeError):
                pass
    return values


def identity(command):
    return command.get('capability_id', 'package'), tuple(normalized(command.get('argv', []))), command.get('stdin', '')


def contract(command):
    return {key: deepcopy(command.get(key, default)) for key, default in {
        'capability_id': 'package', 'argv': [], 'expected_status': 'ok', 'check_kind': 'positive',
        'stdin': '', 'output': '', 'records_key': 'records', 'required_fields': []}.items()}


def pending_commands(previous, cases, checks):
    pending = {identity(item): deepcopy(item) for item in previous}
    failed = {check['capability_id']: check for check in checks if check['status'] == 'failed'}
    for case in cases:
        if case.get('check_kind') == 'contract' or not case.get('argv'):
            continue
        item = contract(case.get('contract', case))
        key = identity(item)
        if case.get('valid') and case.get('status') == 'passed':
            old = pending.get(key)
            if old and all(item[field] == contract(old)[field] for field in
                           ('expected_status', 'check_kind', 'output', 'records_key', 'required_fields')):
                pending.pop(key)
        elif case.get('status') == 'failed':
            pending[key] = {**item, 'reason': case.get('error', '原输入的机器检查失败'),
                            'candidate_version': case.get('candidate_version'),
                            'execution_id': case.get('execution', {}).get('execution_id')}
        check = failed.get(item['capability_id'])
        if (check and case.get('execution', {}).get('execution_id') in check.get('execution_ids', [])):
            pending[key] = {**item, 'reason': check['reason'],
                            'candidate_version': case.get('candidate_version'),
                            'execution_id': case.get('execution', {}).get('execution_id')}
    return list(pending.values())


def prepare_commands(previous, examples, plan, previous_cases=()):
    """兼容旧记录；仅接受 Planner 对同输入、有依据的边界预期修订。"""
    prepared, revisions = [], []
    commands = deepcopy(previous)
    # 旧版本会在语义 passed 时清掉失败队列，从持久用例恢复遗漏的机器失败。
    for case in previous_cases:
        if (case.get('status') == 'failed' and case.get('check_kind') != 'contract' and case.get('argv')
                and not any(identity(item) == identity(case.get('contract', case)) for item in commands)):
            saved = case.get('contract', {key: case[key] for key in
                ('capability_id', 'argv', 'expected_status', 'check_kind') if key in case})
            commands.append({**deepcopy(saved), 'reason': case.get('error', '原输入的机器检查失败')})
    for old in commands:
        same_route = [example for example in examples if example.get('capability_id', 'package') == old.get('capability_id')
                      and normalized(example['argv'], route=True) == normalized(old['argv'], route=True)]
        base = next((example for example in same_route if identity(example) == identity(old)),
                    next(iter(same_route), {}))
        prior = next((case for case in previous_cases if identity(case.get('contract', case)) == identity(old)), {})
        prior_contract = prior.get('contract', {key: prior[key] for key in
            ('expected_status', 'check_kind') if key in prior})
        item = {**contract({**base, **prior_contract, **old}), **deepcopy(old)}
        # 原输入继续遵守当前能力新增的字段要求，保留历史字段和原状态预期。
        item['required_fields'] = list(dict.fromkeys([*item['required_fields'],
            *(field for example in same_route for field in example.get('required_fields', []))]))
        for example in same_route:
            if identity(example) != identity(old) or not example.get('reason') or not example.get('evidence_ids'):
                continue
            try:
                inputs = json.loads(example['argv'][example['argv'].index('--input') + 1])
            except (ValueError, IndexError):
                continue
            registered = any(boundary.get('input') == inputs
                and boundary.get('expected_status') == example.get('expected_status')
                and boundary.get('reason') == example['reason']
                and boundary.get('evidence_ids') == example['evidence_ids']
                for cap in (plan or {}).get('capabilities', []) if cap['id'] == item['capability_id']
                for boundary in cap.get('boundary_cases', []))
            if registered and any(contract(item)[key] != contract(example)[key]
                                  for key in ('expected_status', 'check_kind')):
                revision = {'previous_contract': contract(item), 'revised_contract': contract(example),
                            'reason': example['reason'], 'evidence_ids': deepcopy(example['evidence_ids'])}
                revisions.append(revision)
                item = {**item, **contract(example), 'contract_revision': revision}
        prepared.append(item)
    return prepared, revisions


@dataclass
class ValidationRound:
    version: str
    contract_state: tuple
    index: dict
    contracts: dict
    scope: dict
    previous: dict


class ValidationProgress:
    def __init__(self, package, *, plan, checkpoint):
        self.package, self.plan, self.checkpoint = package, plan, checkpoint
        self.examples, self.examples_locked = [], False
        self.require_host, self.expected_host = True, None
        self.last_validation, self.validation_rounds = {}, 0
        self.max_repair_attempts, self.checked_state = 3, None
        self.active = None
        self._package_preflight = self._function_index_cache = None
        self.record = None

    @property
    def result_store(self):
        return self.package.result_store

    def begin(self):
        index, definitions, scope = self._validation_scope()
        self.active = ValidationRound(self.validation_fingerprint(), self.validation_state(),
            index, definitions, scope, deepcopy(self.last_validation))
        self.validation_rounds += 1
        return self.active

    def end(self):
        self.active = None

    def prepare_review(self, gate, resume=None):
        current = self.active
        targets = set(current.scope['capability_ids'])
        targets.update(case.get('capability_id', 'package') for case in gate.get('case_results', []))
        current.scope['capability_ids'] = [cap for cap in self.capability_ids if cap in targets]
        current.scope['reused_capability_ids'] = [cap for cap in current.scope['reused_capability_ids'] if cap not in targets]
        selected_gate = deepcopy(gate)
        selected_gate['capability_results'] = {cap: item for cap, item in gate.get('capability_results', {}).items() if cap in targets}
        plan = deepcopy(current.contract_state[5])
        if plan is not None:
            plan['capabilities'] = [cap for cap in plan.get('capabilities', []) if cap['id'] in targets]
        examples = [item for item in current.contract_state[1] if item.get('capability_id', 'package') in targets]
        if resume:
            resume = deepcopy(resume)
            resume['plan'], resume['examples'] = deepcopy(plan), deepcopy(examples)
            resume['accepted_checks'] = [check for check in resume.get('accepted_checks', [])
                if check['capability_id'] in targets and check['status'] == 'passed']
            resume['case_results'] = [case for case in resume.get('case_results', [])
                if case.get('capability_id', 'package') in targets
                and current.previous.get('capability_results', {}).get(case.get('capability_id'), {}).get('status') != 'unavailable']
        return deepcopy(dict(candidate_version=current.version, deterministic=selected_gate, plan=plan,
            examples=examples, function_index=current.index, validation_scope=current.scope,
            previous_report=current.previous, resume=resume))

    @property
    def capability_ids(self):
        plan = self.plan()
        return list(dict.fromkeys([cap['id'] for cap in (plan or {}).get('capabilities', [])]
            + [example.get('capability_id') or 'package' for example in self.examples])) or ['package']


    @property
    def capability_states(self):
        return self.current_validation_report().get('capability_results', {})


    @property
    def validation_passed(self):
        return bool(self.current_validation_report().get('valid'))


    def validation_state(self):
        plan = self.plan()
        return (self.package.package_state(), deepcopy(self.examples), self.require_host,
                self.expected_host, self.package.expected_name, deepcopy(plan))


    def validation_fingerprint(self):
        raw = json.dumps(self.validation_state(), ensure_ascii=False, sort_keys=True).encode()
        return hashlib.sha256(raw).hexdigest()


    @staticmethod
    def validate_example_definitions(examples, **_):
        if not isinstance(examples, list) or not examples:
            raise ValueError('validation examples must be a nonempty list')
        for example in examples:
            if not isinstance(example, dict):
                raise ValueError('each validation example must be an object')
            argv = example.get('argv')
            if (not isinstance(argv, list) or len(argv) < 2
                    or not all(isinstance(arg, str) for arg in argv)):
                raise ValueError('example argv must contain an interpreter and script')
            script = Path(argv[1])
            if script.is_absolute() or '..' in script.parts or not script.parts or script.parts[0] != 'scripts':
                raise ValueError('example script must stay under scripts/')
            output = example.get('output', '')
            if not isinstance(output, str) or (output and (Path(output).is_absolute() or '..' in Path(output).parts)):
                raise ValueError('example output must stay in the working directory')
            if example.get('expected_status', 'ok') not in ('ok', 'empty', 'invalid_input'):
                raise ValueError('invalid example expected_status')
            if not isinstance(example.get('records_key', ''), str):
                raise ValueError('example records_key must be a string')
            if 'proxy_mode' in example or any(arg == '--proxy-mode' or arg.startswith('--proxy-mode=') for arg in argv):
                raise ValueError('network configuration belongs in package functions; submit business arguments')


    def set_validation_examples(self, examples):
        self.validate_example_definitions(examples)
        self.examples = deepcopy(examples)
        self.examples_locked = True


    def incomplete_results(self, reason):
        return {cap: {'status': 'incomplete', 'deterministic': 'incomplete',
                      'semantic': 'incomplete', 'reason': reason, 'case_indexes': []}
                for cap in self.capability_ids}


    def function_index(self):
        files = self.package.package_state()
        if self._function_index_cache is None or self._function_index_cache[0] != files:
            index = scan_functions(self.package.output_dir, files, clean=self.result_store.clean)
            self.result_store.root.mkdir(parents=True, exist_ok=True)
            path = self.result_store.root / ('function-index-' + hashlib.sha256(
                json.dumps(files, sort_keys=True).encode()).hexdigest() + '.json')
            path.write_text(json.dumps(self.result_store.clean(index), ensure_ascii=False, indent=2), encoding='utf-8')
            path.chmod(0o600)
            self._function_index_cache = (files, {**index_metadata(index), 'index_file': str(path)})
        return deepcopy(self._function_index_cache[1])


    def _validation_scope(self):
        index = self.function_index()
        plan = self.plan()
        definitions = contracts(self.capability_ids, self.examples, plan,
                               (self.require_host, self.expected_host, self.package.expected_name))
        return index, definitions, validation_scope(index, definitions, self.last_validation)


    def merge_report(self, report):
        if self.active is None:
            return report
        index, definitions, scope, previous = self.active.index, self.active.contracts, self.active.scope, self.active.previous
        report = deepcopy(report)
        report.setdefault('regression_commands', deepcopy(previous.get('regression_commands', [])))
        reused = set(scope['reused_capability_ids'])
        report['case_results'] = [case for case in report.get('case_results', [])
                                  if case.get('capability_id', 'package') not in reused]
        bindings = function_bindings(index, report.get('case_results', []), retained={
            cap: previous['function_bindings'][cap] for cap in scope['reused_capability_ids']})
        return {**merge_reused(report, previous, scope['reused_capability_ids']),
                'function_index': index, 'function_contracts': definitions,
                'function_bindings': bindings, 'validation_scope': scope}


    def current_validation_report(self):
        fingerprint = self.validation_fingerprint()
        if self.last_validation.get('candidate_fingerprint') == fingerprint:
            return self.validation_feedback(self.last_validation)
        _, _, scope = self._validation_scope()
        results = self.incomplete_results('当前候选版本尚未完成验收。')
        for cap in scope['reused_capability_ids']:
            results[cap] = deepcopy(self.last_validation['capability_results'][cap])
        return self.validation_feedback({'valid': False, 'package_valid': False, 'stage': 'pending',
                'candidate_fingerprint': fingerprint,
                'capability_results': results, 'validation_scope': scope,
                'validation_rounds': self.validation_rounds})


    def validation_feedback(self, report):
        report = deepcopy(report)
        for command in report.get('regression_commands', []):
            item = report.get('capability_results', {}).get(command.get('capability_id'), {})
            if item.get('status') == 'available':
                item.update(status='incomplete', reason='原失败输入尚未完成补验。')
                report.update(valid=False, report_complete=False)
        index = self.function_index()
        tasks = []
        if not report.get('package_valid') and report.get('error'):
            tasks.append({'action': 'repair_package', 'reason': report['error'],
                          'expected_name': self.package.expected_name, 'expected_host': self.expected_host})
        for cap, item in report.get('capability_results', {}).items():
            if item.get('status') == 'available':
                continue
            contract = next((case for case in report.get('case_results', [])
                             if case.get('capability_id', 'package') == cap
                             and case.get('check_kind') == 'contract'), {})
            action = ('repair_contract' if contract else
                      'submit_validation' if report.get('stage') in {'pending', 'preflight'} else
                      'repair_package' if not report.get('package_valid') else
                      'repair_code' if item.get('status') == 'unavailable' else 'complete_validation')
            failed = next((case for case in report.get('case_results', [])
                           if case.get('capability_id', 'package') == cap and case.get('status') == 'failed'), {})
            example = next((case for case in self.examples
                            if case.get('capability_id', 'package') == cap
                            and case.get('expected_status', 'ok') == 'ok'
                            and case.get('check_kind') != 'boundary'), {})
            tasks.append({'capability_id': cap, 'action': action,
                          'reason': contract.get('error') or item.get('reason', report.get('error', '当前版本尚未完成验收。')),
                          'argv': failed.get('argv') or contract.get('argv') or example.get('argv')})
            bindings = report.get('function_bindings') or self.last_validation.get('function_bindings', {})
            identifiers = bindings.get(cap, {}).get('function_ids', [])
            entry = (tasks[-1]['argv'] or [None, None])[1]
            if not identifiers:
                identifiers = [key for key, item in index['functions'].items() if item['path'] == entry]
            identifiers = sorted(identifiers, key=lambda key: (
                index['functions'].get(key, {}).get('name') != cap, key))
            tasks[-1]['functions'] = [{'function_id': key, **{name: index['functions'][key][name]
                for name in ('path', 'lineno', 'end_lineno', 'read_file', 'end_offset', 'sha256')}}
                for key in identifiers if key in index['functions']]
            if entry in self.package.files:
                tasks[-1]['read_file'] = {'path': entry}
            tasks[-1]['regression_commands'] = [deepcopy(command) for command in
                report.get('regression_commands', self.last_validation.get('regression_commands', []))
                if command.get('capability_id') == cap]
        if not self.examples:
            tasks.append({'action': 'provide_examples', 'reason': '提交完整业务 CLI 样例后启动独立验收。'})
        report['next_actions'] = tasks
        report['package_files'] = sorted(self.package.package_state())
        report['function_index_file'] = index['index_file']
        return report


    def package_preflight(self):
        """按当前版本反馈静态缺项，供 Builder 修包；不消耗独立验收轮次。"""
        fingerprint = self.validation_fingerprint()
        if self._package_preflight is not None and self._package_preflight[0] == fingerprint:
            return deepcopy(self._package_preflight[1])
        gate = validate_access_preflight(self.package.output_dir, self.package.expected_name, self.examples,
            require_host=self.require_host, expected_host=self.expected_host)
        report = self.validation_feedback({**gate, 'candidate_fingerprint': fingerprint,
            'preflight_valid': bool(gate.get('package_valid') and not gate.get('error'))})
        self._package_preflight = (fingerprint, report)
        if self.record:
            self.record.event('builder_preflight', version=fingerprint,
                              report=self.result_store.present(report))
        return deepcopy(report)


    def checkpoint_validation_progress(self, report):
        if self.active is not None and self.active.version == self.validation_fingerprint():
            self.last_validation = {**self.merge_report(deepcopy(report)), 'candidate_fingerprint': self.active.version,
                                    'validation_rounds': self.validation_rounds}
            self.checkpoint()


class ValidationReview:
    """固定候选的一次验收：执行观察、机器结论、语义提交和原失败补验。"""
    def __init__(self, record, on_progress):
        self.record, self.on_progress = record, on_progress
        self.state, self.previous_regression_commands = {}, []
        self.path = None

    def start(self, *, candidate_dir, candidate_version, deterministic, host, notes,
              plan=None, examples=None, resume=None, function_index=None, validation_scope=None,
              previous_report=None):
        """冻结本轮输入，恢复同版本证据，并登记静态检查观察。"""
        previous_report = previous_report or {}
        self.previous_regression_commands = deepcopy(previous_report.get("regression_commands", []))
        self.previous_regression_commands, revisions = prepare_commands(
            self.previous_regression_commands, examples or [], plan, previous_report.get('case_results', []))
        session_id = uuid4().hex
        self.path = self.record.root / f"validation-{session_id}.json"
        self.state = {"id": session_id, "host": host, "notes": notes,
                      "candidate_version": candidate_version, "plan": deepcopy(plan),
                      "function_index": deepcopy(function_index), "validation_scope": deepcopy(validation_scope),
                      "files": sorted(path.relative_to(candidate_dir).as_posix()
                                      for path in candidate_dir.rglob("*") if path.is_file()),
                      "examples": deepcopy(examples or []), "static_validation": deepcopy(deterministic),
                      "deterministic": deepcopy(deterministic),
                      "case_results": deepcopy(deterministic.get("case_results", [])),
                      "observations": [], "responses": [], "usage": {}, "calls": 0}
        self.state['regression_contract_revisions'] = revisions
        if (isinstance(resume, dict) and resume.get("candidate_version") == candidate_version
                and resume.get("plan") == plan and resume.get("examples") == (examples or [])
                and not resume.get("cancelled") and not resume.get("result", {}).get("cancelled")):
            self.state["observations"] = deepcopy(resume.get("observations", []))
            self.state["resumed_from"] = resume.get("id")
            if "repair_budget" in resume:
                self.state["repair_budget"] = validate_repair_budget(resume["repair_budget"])
            self.state["case_results"].extend(deepcopy(case) for case in resume.get("case_results", [])
                if case.get("check_kind") != "contract" and case.get("candidate_version") == candidate_version
                and case.get("observation_id"))
        self._refresh_deterministic()
        gate = self.observe("static_checks", {}, deterministic)
        self.state["gate_observation_id"] = gate["observation_id"]
        if self.state.get("resumed_from"):
            checks = [{key: deepcopy(check[key]) for key in ("capability_id", "status", "reason")}
                      for check in resume.get("accepted_checks", []) if check.get("status") in {"passed", "failed"}]
            if checks:
                self.submit({"checks": checks})
        self.on_progress(self.result())
        return gate

    def save(self):
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self.record.clean(self.state), ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        temporary.chmod(0o600)
        temporary.replace(self.path)


    def observe(self, name, args, result):
        oid = f"validation-{self.state['id']}-obs-{len(self.state['observations']) + 1}"
        case = result.get("validation") if name == "exec" else None
        reopen = False
        if case is not None:
            case = deepcopy(case)
            case.update(observation_id=oid, candidate_version=self.state["candidate_version"])
            key = (identity(case.get('contract', case)), case["check_kind"])
            previous = next((index for index, item in enumerate(self.state["case_results"])
                             if (identity(item.get('contract', item)), item["check_kind"]) == key), None)
            if previous is None:
                self.state["case_results"].append(case)
            else:
                replaced = self.state["case_results"][previous].get("execution", {}).get("execution_id")
                reopen = any(check["capability_id"] == case["capability_id"]
                             and replaced in check.get("execution_ids", [])
                             for check in self.state.get("accepted_checks", []))
                case["example"] = self.state["case_results"][previous]["example"]
                self.state["case_results"][previous] = case
            result = {**result, "validation": case}
        self.state["observations"].append(
            {"id": oid, "tool": name, "args": deepcopy(args), "result": deepcopy(result)}
        )
        if case is not None:
            self._refresh_deterministic()
            if reopen:
                self.state["accepted_checks"] = [check for check in self.state["accepted_checks"]
                    if check["capability_id"] != case["capability_id"]]
                self.state.setdefault("protocol_errors", {})[case["capability_id"]] = "支持结论的执行已更新，请核对新结果并重新提交。"
                self.state["partial_report"] = self._semantic_report()
                self.state["report_complete"] = False
        self.save()
        if case is not None:
            self.on_progress(self.result())
        return {"observation_id": oid, **result}


    def _refresh_deterministic(self):
        static = self.state["static_validation"]
        if not static.get("package_valid"):
            self.state["deterministic"] = deepcopy(static)
            return
        summary = _summarize_cases(self.state["case_results"]) if self.state["case_results"] else {}
        capabilities = deepcopy(static.get("capability_results", {}))
        capabilities.update(summary.get("capability_results", {}))
        for cap, item in capabilities.items():
            positive = any(case.get("capability_id") == cap and case.get("check_kind") == "positive"
                           and case.get("expected_status", "ok") == "ok" and case.get("valid")
                           for case in self.state["case_results"])
            if item.get("deterministic") == "passed" and not positive:
                item.update(status="incomplete", deterministic="incomplete", reason="尚无正常业务调用通过机器检查。")
        valid = bool(capabilities) and all(item.get("deterministic") == "passed" for item in capabilities.values())
        self.state["deterministic"] = {**deepcopy(static), **summary, "valid": valid,
            "stage": "complete" if valid else "examples", "capability_results": capabilities,
            "case_results": deepcopy(self.state["case_results"]), "examples": len(self.state["case_results"])}


    def capabilities(self):
        plan = self.state.get("plan") or {}
        ids = [cap["id"] for cap in plan.get("capabilities", [])]
        ids.extend(example.get("capability_id") or "package" for example in self.state["examples"])
        ids.extend(self.state["deterministic"].get("capability_results", {}))
        ids.extend(case.get("capability_id") or "package" for case in self.state["case_results"])
        return list(dict.fromkeys(ids or ["package"]))


    def _capability_results(self):
        gate = self.state["deterministic"]
        checks = {check["capability_id"]: check for check in self.state.get("accepted_checks", [])}
        results = {}
        for capability in self.capabilities():
            fixed = gate.get("capability_results", {}).get(capability, {})
            cases = [case for case in self.state["case_results"]
                     if (case.get("capability_id") or "package") == capability]
            states = [case.get("status", "passed" if case.get("valid") else "failed") for case in cases]
            det = fixed.get("deterministic")
            if det not in {"passed", "failed", "incomplete"}:
                det = ("failed" if "failed" in states else "passed"
                       if states and all(state == "passed" for state in states) else "incomplete")
            check = checks.get(capability)
            sem = check["status"] if check and check["status"] != "uncertain" else "incomplete"
            reason = check["reason"] if check else "尚无有效语义结论"
            if not gate.get("package_valid"):
                status, det, sem = "incomplete", "incomplete", "incomplete"
                reason = gate.get("error", "包结构尚未通过检查")
            elif det == "failed" or sem == "failed":
                status = "unavailable"
            else:
                status = "available" if det == sem == "passed" else "incomplete"
                if any(item['capability_id'] == capability for item in self._regression_commands()):
                    status, reason = 'incomplete', '原失败输入尚未完成补验。'
            if gate.get("package_valid") and det != "passed":
                reason = fixed.get("reason") or next(
                    (case.get("error") for case in cases if case.get("error")), "业务执行的机器检查尚未完成。")
            item = {"status": status, "deterministic": det, "semantic": sem, "reason": reason,
                    "case_indexes": fixed.get("case_indexes", [case["example"] for case in cases])}
            if gate.get("package_valid") and check is None:
                item["protocol_error"] = self.state.get("protocol_errors", {}).get(
                    capability, "尚未通过 send_message 向 builder 提交本能力的有效结论")
                if status == "incomplete":
                    item["reason"] = item["protocol_error"]
            results[capability] = item
        return results


    def execution_example(self, args):
        capability, argv = args["capability_id"], args["argv"]
        regression = next((item for item in self._regression_commands() if identity(item) == identity(args)), None)
        if regression:
            for field in ('expected_status', 'check_kind'):
                if field in args and args[field] != regression[field]:
                    raise ValueError(f'regression {field} must retain the original expectation; ask planner to revise it')
            return {**contract(regression), 'argv': deepcopy(argv)}
        own = [item for item in self.state["examples"]
               if (item.get("capability_id") or "package") == capability
               and normalized(item["argv"], route=True) == normalized(argv, route=True)]
        other = [item for item in self.state["examples"]
                 if (item.get("capability_id") or "package") != capability
                 and normalized(item["argv"], route=True) == normalized(argv, route=True)]
        if not own or other and not any(normalized(item["argv"]) == normalized(argv) for item in own):
            raise ValueError("CLI argv must use this capability's normal business route; use its suggested command")
        boundary = next((item for item in own if normalized(item["argv"]) == normalized(argv)
                         and (item.get("check_kind") == "boundary" or item.get("expected_status", "ok") != "ok")), None)
        positives = [item for item in own if item.get("check_kind") != "boundary"
                     and item.get("expected_status", "ok") == "ok"]
        exact = next((item for item in positives if normalized(item["argv"]) == normalized(argv)), None)
        selected = deepcopy(boundary or exact or (positives or own)[0])
        expected = args.get("expected_status", selected.get("expected_status", "ok") if boundary else "ok")
        if boundary and expected != boundary.get("expected_status", "ok"):
            raise ValueError("expected_status conflicts with this registered boundary example")
        kind = "boundary" if boundary or expected != "ok" else args.get("check_kind", "positive")
        selected.update(capability_id=capability, argv=deepcopy(argv), expected_status=expected,
                        check_kind=kind, stdin=args.get('stdin', ''))
        selected["required_fields"] = list(dict.fromkeys(
            field for item in positives or [selected] for field in item.get("required_fields", [])))
        return selected


    def _cli_evidence(self, capability, *, successful):
        observations = {item["id"]: item for item in self.state["observations"]}
        evidence = []
        for case in self.state["case_results"]:
            observation = observations.get(case.get("observation_id"), {})
            args, result = observation.get("args", {}), observation.get("result", {})
            eid, argv = result.get("execution_id"), args.get("argv")
            if (case.get("capability_id") != capability or observation.get("tool") != "exec"
                    or args.get("capability_id") != capability or not isinstance(argv, list) or not argv
                    or result.get("started") is False or not eid or {"--help", "-h"}.intersection(argv)
                    or identity(case.get('contract', case)) != identity(args)
                    or case.get("execution", {}).get("execution_id") != eid
                    or case.get("candidate_version") != self.state["candidate_version"]):
                continue
            if successful and (case.get("status") != "passed" or not case.get("valid")
                    or case.get("check_kind") != "positive" or case.get("expected_status", "ok") != "ok"
                    or result.get("status") != "completed" or result.get("exit_code") != 0
                    or result.get("error") or result.get("timed_out") or result.get("cancelled")
                    or args.get("proxy_mode") is not None or result.get("diagnostic_network_override")
                    or any(value == "--proxy-mode" or value.startswith("--proxy-mode=") for value in argv)):
                continue
            evidence.append((eid, observation["id"]))
        return list(dict.fromkeys(evidence))


    def progress(self):
        accepted = {check["capability_id"]: check["status"] for check in self.state.get("accepted_checks", [])}
        pending = [cap for cap in self.capabilities() if accepted.get(cap) not in {"passed", "failed"}]
        missing = [cap for cap in pending if not self._cli_evidence(cap, successful=True)]
        commands = []
        for cap in missing:
            example = next((example for example in self.state["examples"]
                            if (example.get("capability_id") or "package") == cap
                            and example.get("expected_status", "ok") == "ok"
                            and example.get("check_kind") != "boundary"), None)
            if example is not None:
                commands.append({"capability_id": cap, "argv": deepcopy(example["argv"])})
        return {"accepted_capabilities": accepted, "pending_capabilities": pending,
                "pending_regressions": self._regression_instructions(),
                "missing_independent_cli": missing, "suggested_commands": commands,
                "validation_scope": self.state.get('validation_scope'),
                "function_index_file": (self.state.get('function_index') or {}).get('index_file'),
                "repair_budget": deepcopy(self.state.get("repair_budget"))}


    def _semantic_report(self):
        checks = deepcopy(self.state.get("accepted_checks", []))
        questions = [check["intent_question"] for check in checks if check.get("intent_question")]
        complete = set(self.capabilities()) <= {check["capability_id"] for check in checks}
        status = ("needs_intent" if questions else "passed"
                  if complete and all(check["status"] == "passed" for check in checks) else "partial")
        report = {"status": status, "checks": checks,
                  "summary": "; ".join(f"{check['capability_id']}: {check['reason']}" for check in checks)
                  or "尚未提交有效能力结论"}
        if questions:
            report["intent_question"] = "\n".join(dict.fromkeys(questions))
        return report


    def submit(self, content):
        required = set(self.capabilities())
        if (not isinstance(content, dict) or "checks" not in content
                or set(content) - {"checks", "repair_budget"} or not isinstance(content["checks"], list)):
            raise ValueError("builder content requires checks, an array of capability verdicts, and optional repair_budget")
        if "repair_budget" in content:
            self.state["repair_budget"] = validate_repair_budget(content["repair_budget"])
        accepted = {check["capability_id"]: deepcopy(check) for check in self.state.get("accepted_checks", [])}
        errors, protocol_errors = [], self.state.setdefault("protocol_errors", {})
        ids = [check.get("capability_id") for check in content["checks"] if isinstance(check, dict)]
        duplicates = {cap for cap in ids if isinstance(cap, str) and ids.count(cap) > 1}
        for index, check in enumerate(content["checks"]):
            capability = check.get("capability_id") if isinstance(check, dict) else None
            try:
                if not isinstance(check, dict):
                    raise ValueError(f"checks[{index}] must be an object")
                if not isinstance(capability, str) or capability not in required:
                    raise ValueError(f"checks[{index}].capability_id must identify an existing capability")
                if capability in duplicates:
                    raise ValueError(f"{capability}: submit one verdict per capability")
                if set(check) - {"capability_id", "status", "reason", "intent_question", "execution_ids"}:
                    raise ValueError(f"{capability}: unknown capability verdict fields")
                status = check.get("status")
                if status not in {"passed", "failed", "uncertain"}:
                    raise ValueError(f"{capability}: status must be passed, failed or uncertain")
                if not isinstance(check.get("reason"), str) or not check["reason"].strip():
                    raise ValueError(f"{capability}: reason must explain the observed result or unverified scope")
                question = check.get("intent_question")
                if question is not None and (status != "uncertain" or not isinstance(question, str) or not question.strip()):
                    raise ValueError(f"{capability}: intent_question requires uncertain and nonempty text")
                evidence = self._cli_evidence(capability, successful=status == "passed")
                if status == 'passed' and any(item['capability_id'] == capability for item in self._regression_commands()):
                    raise ValueError(f'{capability}: pending regression inputs require successful CLI reruns with their original expectations')
                # 旧报告中的 execution_ids 由当前会话的真实证据覆盖。
                if status in {"passed", "failed"} and not evidence:
                    raise ValueError(f"{capability}: {status} requires an independent "
                                     + ("successful " if status == "passed" else "")
                                     + "CLI argv execution"
                                     + (" using this capability's normal business route" if status == "passed"
                                        else " with a recorded machine check"))
                purpose = next((cap.get("purpose", capability)
                                for cap in (self.state.get("plan") or {}).get("capabilities", [])
                                if cap["id"] == capability), capability)
                accepted[capability] = {**deepcopy(check), "requirement": purpose,
                                       "execution_ids": list(dict.fromkeys(eid for eid, _ in evidence)),
                                       "evidence_ids": list(dict.fromkeys(oid for _, oid in evidence))}
                protocol_errors.pop(capability, None)
            except (ValueError, TypeError) as exc:
                message = str(exc)
                errors.append(message)
                if isinstance(capability, str) and capability in required and capability not in accepted:
                    protocol_errors[capability] = message
        self.state["accepted_checks"] = list(accepted.values())
        missing = sorted(required - accepted.keys())
        for capability in missing:
            protocol_errors.setdefault(capability, "尚未通过 send_message 向 builder 提交本能力的有效结论")
        self.state["partial_report"] = self._semantic_report()
        self.state["report_complete"] = not missing
        self.state.setdefault("report_errors", []).extend(errors)
        self.state["capability_results"] = self._capability_results()
        self.save()
        self.on_progress(self.result())
        receipt = {"accepted_capabilities": sorted(accepted), "pending_capabilities": missing,
                   "pending_regressions": self._regression_instructions(),
                   "report_complete": not missing, "protocol_errors": deepcopy(protocol_errors)}
        if "repair_budget" in self.state:
            receipt["repair_budget"] = deepcopy(self.state["repair_budget"])
        if errors or missing:
            receipt["error"] = "; ".join(errors + (["missing capability verdicts: " + ", ".join(missing)] if missing else []))
        return receipt


    def _regression_commands(self):
        return pending_commands(self.previous_regression_commands, self.state['case_results'],
                                self.state.get('accepted_checks', []))


    def _regression_instructions(self):
        return [{**item, 'exec': {key: deepcopy(item[key]) for key in
            ('capability_id', 'argv', 'stdin', 'expected_status', 'check_kind')}}
            for item in self._regression_commands()]


    def result(self, *, error=""):
        gate = self.state["deterministic"]
        capabilities = self._capability_results()
        passed = bool(capabilities) and all(item["status"] == "available" for item in capabilities.values())
        result = {**deepcopy(gate), "valid": passed, "package_valid": bool(gate.get("package_valid")),
                  "case_results": deepcopy(self.state["case_results"]), "capability_results": capabilities,
                  "candidate_version": self.state["candidate_version"], "validation_session": str(self.path),
                  "validation_usage": deepcopy(self.state["usage"]),
                  "report_complete": not gate.get("package_valid") or bool(self.state.get("report_complete")),
                  "regression_commands": self._regression_commands()}
        result['regression_contract_revisions'] = deepcopy(self.state.get('regression_contract_revisions', []))
        if not passed and "repair_budget" in self.state:
            result["repair_budget"] = deepcopy(self.state["repair_budget"])
        if self.state.get("resumed_from"):
            result["resumed_from"] = self.state["resumed_from"]
        semantic = self.state.get("partial_report")
        if semantic is not None:
            result["semantic_report"] = deepcopy(semantic)
            if gate.get("package_valid"):
                result["stage"] = "complete" if passed else "semantic_validation"
        protocols = {cap: item["protocol_error"] for cap, item in capabilities.items() if item.get("protocol_error")}
        reasons = [gate["error"]] if gate.get("error") else []
        if semantic is not None and not passed:
            reasons.append(semantic["summary"])
        if error:
            reasons.append(error)
            if gate.get("error"):
                result["semantic_error"] = error
        if protocols:
            result["protocol_errors"] = protocols
            result["report_errors"] = list(dict.fromkeys(protocols.values()))
            reasons.extend(result["report_errors"])
        if reasons:
            result["error"] = "; ".join(dict.fromkeys(reasons))
        return result
