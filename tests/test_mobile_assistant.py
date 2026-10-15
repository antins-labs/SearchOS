"""Personal mobile service contracts. No external models, network or push delivery."""
import asyncio
import base64
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'web'))
from api.assistant import runtime as rt
from api.assistant.auth import AccessMiddleware, Config, COOKIE, digest, ensure_admin_secret
from api.assistant.routes import router
from api.assistant.scheduling import ScheduleInput, in_quiet_hours, next_occurrence
from api.assistant.push import validate_subscription
from api.assistant.store import encode


def stamp(text):
    return datetime.fromisoformat(text).timestamp()


@pytest.fixture
def service(tmp_path, monkeypatch):
    service = rt.AssistantRuntime(Config(tmp_path))
    monkeypatch.setattr(rt, '_runtime', service)
    monkeypatch.setattr(rt, 'sessions', {})
    monkeypatch.setattr(rt, 'WORKSPACE_ROOT', str(tmp_path / 'workspaces'))
    return service


def client_for(service):
    app = FastAPI()
    app.add_middleware(AccessMiddleware)
    app.include_router(router)
    @app.get('/api/history')
    def history():
        return {'private': True}
    @app.websocket('/api/ws/test')
    async def socket(ws: WebSocket):
        await ws.accept()
        while True:
            await ws.receive_text()
            await ws.send_text('ok')
    return TestClient(app, base_url='https://search.example.test' if service.config.remote else 'http://testserver')


def auth_headers():
    return {'Origin': 'https://search.example.test', 'X-SearchOS-Request': '1'}


def remote(service):
    service.config.public_origin = 'https://search.example.test'
    return client_for(service)


def login(client, service):
    return client.post('/api/assistant/login', json={'token': ensure_admin_secret(service.config).read_text()}, headers=auth_headers())


def payload(**kw):
    return ScheduleInput(title='日报', instruction='整理近期变化', **kw).model_dump(exclude={'version'})


def create(client, **kw):
    response = client.post('/api/assistant/schedules', json=payload(**kw), headers={'Idempotency-Key': 'schedule-test-1'})
    assert response.status_code == 200, response.text
    return response.json()


def test_dates_dst_and_quiet_hours():
    daily = payload(time='08:00')
    assert next_occurrence(daily, stamp('2026-10-14T07:59:00+08:00')) == stamp('2026-10-14T08:00:00+08:00')
    assert next_occurrence(daily, stamp('2026-10-14T08:00:00+08:00')) == stamp('2026-10-15T08:00:00+08:00')
    weekly = payload(frequency='weekly', weekday=1)
    assert next_occurrence(weekly, stamp('2026-10-14T08:00:00+08:00')) == stamp('2026-10-19T08:00:00+08:00')
    gap = payload(time='02:30', timezone='America/New_York')
    assert next_occurrence(gap, stamp('2026-03-08T00:00:00-05:00')) == stamp('2026-03-09T02:30:00-04:00')
    fold = payload(time='01:30', timezone='America/New_York')
    assert next_occurrence(fold, stamp('2026-11-01T01:31:00-04:00')) == stamp('2026-11-02T01:30:00-05:00')
    once = payload(frequency='once', date='2026-10-14')
    assert next_occurrence(once, stamp('2026-10-15T00:00:00+08:00')) is None
    prefs = {**rt.DEFAULT_PREFERENCES, 'quiet_enabled': True}
    assert in_quiet_hours(prefs, stamp('2026-10-14T23:00:00+08:00'))
    assert in_quiet_hours(prefs, stamp('2026-10-15T07:59:00+08:00'))
    assert not in_quiet_hours(prefs, stamp('2026-10-15T08:00:00+08:00'))


def test_host_health_detects_stalled_failed_and_stopped_scheduler(service, monkeypatch):
    now = time.time()
    monkeypatch.setattr(rt.time, 'time', lambda: now)
    monkeypatch.setenv('SF_SERVICE_MANAGED', 'launchd')
    monkeypatch.setenv('SF_SERVICE_KEEP_AWAKE', 'ac')
    service.leader = True
    service.tasks = [SimpleNamespace(done=lambda: False)]
    service.last_tick = now - 2
    with client_for(service) as client:
        health = client.get('/api/assistant/status').json()
        assert health['scheduler_running'] is True
        assert health['service_mode'] == 'managed'
        assert health['keep_awake'] == 'ac'
        assert health['uptime_seconds'] >= 0
        assert health['instance_id'] == service.instance_id
        service.last_tick = now - 20
        assert client.get('/api/assistant/status').json()['scheduler_running'] is False
        service.last_tick = now
        service.tick_failed = True
        assert client.get('/api/assistant/status').json()['scheduler_running'] is False
        service.tick_failed = False
        service.tasks = [SimpleNamespace(done=lambda: True)]
        assert client.get('/api/assistant/status').json()['scheduler_running'] is False
        service.tasks = []
        assert client.get('/api/assistant/status').json()['scheduler_running'] is False


def test_host_status_requires_remote_authentication(service):
    with remote(service) as client:
        assert client.get('/api/assistant/status').status_code == 401


def test_validation_scope_and_invalid_time():
    for kw in ({'timezone': 'Nowhere'}, {'time': '24:00'}, {'frequency': 'once'}, {'sources': {'mode': 'local'}}, {'instruction': '  '}):
        with pytest.raises(ValueError):
            ScheduleInput(**{'title': 'a', 'instruction': 'b', **kw})


def test_plan_idempotency_versions_and_actions(service):
    with client_for(service) as client:
        plan = create(client)
        assert create(client)['id'] == plan['id']
        assert len(client.get('/api/assistant/schedules').json()) == 1
        edit = payload()
        edit['version'] = 0
        assert client.put('/api/assistant/schedules/' + plan['id'], json=edit).status_code == 409
        base = '/api/assistant/schedules/' + plan['id']
        request = {'json': {'version': 1}, 'headers': {'Idempotency-Key': 'run-now-test'}}
        first = client.post(base + '/run-now', **request)
        assert first.status_code == 200
        assert client.post(base + '/run-now', **request).json()['id'] == first.json()['id']
        assert client.post(base + '/run-now', json={'version': 1}, headers={'Idempotency-Key': 'run-now-test-2'}).status_code == 409
        assert client.post(base + '/resume', json={'version': 1}).status_code == 200
        assert client.post(base + '/pause', json={'version': 1}).status_code == 409
        assert client.post(base + '/pause', json={'version': 2}).status_code == 200
        assert client.post(base + '/delete', json={'version': 3}).status_code == 200
        assert client.get('/api/assistant/schedules').json() == []
        assert service.store.one('SELECT status FROM runs')['status'] == 'skipped'


def test_auth_pairing_csrf_and_revocation(service):
    with remote(service) as client:
        assert client.get('/api/history').status_code == 401
        assert client.get('/api/assistant/access').json()['authenticated'] is False
        assert client.post('/api/assistant/login', json={'token': 'wrong'}).status_code == 403
        response = login(client, service)
        assert response.status_code == 200
        cookie = response.headers['set-cookie']
        assert 'HttpOnly' in cookie and 'Secure' in cookie and 'SameSite=strict' in cookie
        assert client.get('/api/history').status_code == 200
        assert client.post('/api/assistant/pairings').status_code == 403
        code = client.post('/api/assistant/pairings', headers=auth_headers()).json()['code']
        owner_cookie = client.cookies.get(COOKIE)
        assert service.store.one('SELECT code_hash FROM pairings')['code_hash'] != code
        with client_for(service) as phone:
            claimed = phone.post('/api/assistant/pairings/claim', json={'code': code}, headers=auth_headers())
            assert claimed.status_code == 200
            assert phone.get('/api/history').status_code == 200
            assert phone.post('/api/assistant/pairings', headers=auth_headers()).status_code == 403
            assert phone.post('/api/assistant/pairings/claim', json={'code': code}, headers=auth_headers()).status_code == 401
            device_id = claimed.json()['id']
            assert client.delete('/api/assistant/devices/' + device_id, headers=auth_headers()).status_code == 200
            assert phone.get('/api/history').status_code == 401
        assert owner_cookie not in str(service.store.rows('SELECT * FROM devices'))
        assert client.get('/api/history', headers={'Origin': 'https://evil.test'}).status_code == 403


def test_pairing_expiry_and_limits(service):
    with remote(service) as client:
        assert login(client, service).status_code == 200
        code = client.post('/api/assistant/pairings', headers=auth_headers()).json()['code']
        service.store.execute('UPDATE pairings SET expires=0')
        assert client.post('/api/assistant/pairings/claim', json={'code': code}, headers=auth_headers()).status_code == 401
        for _ in range(10):
            result = client.post('/api/assistant/pairings/claim', json={'code': '00000000'}, headers=auth_headers())
        assert result.status_code == 429


def test_local_rejects_foreign_host_and_origin(service):
    with client_for(service) as client:
        assert client.get('/api/history').status_code == 200
        assert client.get('/api/history', headers={'Host': 'public.example'}).status_code == 401
        assert client.get('/api/history', headers={'X-Forwarded-Host': 'public.example'}).status_code == 401
        assert client.post('/api/assistant/schedules', headers={'Origin': 'https://evil.test'}, json=payload()).status_code == 403


@pytest.mark.asyncio
async def test_schedule_due_once_skip_overlap_and_recovery(service, monkeypatch):
    with client_for(service) as client:
        plan = create(client)
    now = time.time()
    service.store.execute('UPDATE schedules SET active=1,next_run=?', (now-30,))
    launched = []
    async def launch(key):
        launched.append(key)
        service.store.execute("UPDATE runs SET status='running',session_id='mock' WHERE id=?", (key,))
        rt.sessions['mock'] = {'status': 'running', 'assistant_run_id': key}
    monkeypatch.setattr(service, 'launch', launch)
    await service.tick(now)
    await service.tick(now)
    assert len(launched) == 1
    service.store.execute('UPDATE schedules SET active=1,next_run=?', (now+10,))
    await service.tick(now+20)
    assert len(launched) == 1  # Busy engine leaves due schedule pending.
    await service.tick(now+3700)
    assert service.store.one("SELECT count(*) AS n FROM runs WHERE status='skipped'")['n'] == 1
    assert service.store.one('SELECT count(*) AS n FROM notifications')['n'] == 1
    row = service.store.one("SELECT * FROM runs WHERE status='running'")
    rt.sessions.clear()
    result = Path(rt.WORKSPACE_ROOT) / 'mock/output/result.json'
    result.parent.mkdir(parents=True)
    result.write_text('{"answer":"old answer"}')
    os.utime(result, (now-100, now-100))
    await service.recover_run(row)
    assert service.store.one('SELECT status FROM runs WHERE id=?', (row['id'],))['status'] == 'interrupted'


@pytest.mark.asyncio
async def test_report_snapshot_is_immutable_and_notification_once(service, monkeypatch):
    from api.routes import history
    answer = {'answer': 'original', 'query': 'test', 'session_id': 'session', 'search_state': {}}
    async def load(_): return answer
    monkeypatch.setattr(history, 'load_history', load)
    rt.sessions['session'] = {'status': 'completed'}
    service.track_session('session')
    await service.before_replace('session')
    first = service.store.one('SELECT * FROM reports')
    assert json.loads(first['payload'])['answer'] == 'original'
    answer['answer'] = 'follow-up'
    await service.before_replace('session')
    await service.tick()
    assert service.store.one('SELECT count(*) AS n FROM notifications')['n'] == 1
    assert json.loads(service.store.one('SELECT payload FROM reports')['payload'])['answer'] == 'original'


def test_push_subscription_rejects_ssrf():
    enc = lambda b: base64.urlsafe_b64encode(b).rstrip(b'=').decode()
    subscription = {'endpoint': 'https://web.push.apple.com/example', 'keys': {'p256dh': enc(b'\x04'+b'x'*64), 'auth': enc(b'x'*16)}}
    assert validate_subscription(subscription)['endpoint'] == subscription['endpoint']
    for endpoint in ('http://web.push.apple.com/x', 'https://127.0.0.1/x', 'https://web.push.apple.com.evil.test/x', 'https://user@web.push.apple.com/x', 'https://web.push.apple.com:8000/x'):
        with pytest.raises(ValueError): validate_subscription({**subscription, 'endpoint': endpoint})


@pytest.mark.asyncio
async def test_push_retry_does_not_rerun_search(service, monkeypatch):
    now = time.time()
    store = service.store
    store.execute('INSERT INTO devices(id,name,token_hash,created,last_seen,expires) VALUES(?,?,?,?,?,?)', ('d','phone','hash',now,now,now+86400))
    store.execute('INSERT INTO subscriptions VALUES(?,?,?,?,?)', ('s','d','endpoint','{}',now))
    store.execute('INSERT INTO notifications(id,kind,title,body,url,created) VALUES(?,?,?,?,?,?)', ('n','completed','test','body','/m',now))
    store.execute("INSERT INTO outbox(id,notification_id,subscription_id,status,next_try) VALUES('o','n','s','pending',?)", (now,))
    def fail(*_): raise RuntimeError('offline')
    service.push = SimpleNamespace(ready=True, send=fail)
    await service.deliver_push(now)
    assert store.one('SELECT attempts,status FROM outbox') == {'attempts': 1, 'status': 'pending'}
    assert not store.rows('SELECT * FROM runs')
    service.push.send = lambda *_: 'gone'
    await service.deliver_push(now+120)
    assert store.one('SELECT status FROM outbox')['status'] == 'expired'
    assert not store.rows('SELECT * FROM subscriptions')


@pytest.mark.asyncio
async def test_single_worker_guard(service):
    other = rt.AssistantRuntime(service.config)
    await service.start()
    try:
        with pytest.raises(RuntimeError): await other.start()
    finally:
        await service.stop()


def test_all_read_panels_and_preferences(service):
    with client_for(service) as client:
        plan = create(client)
        for path in ('/access','/status','/devices','/schedules','/inbox','/push/config','/preferences',f"/schedules/{plan['id']}/runs"):
            response = client.get('/api/assistant' + path)
            assert response.status_code == 200, (path, response.text)
            assert response.headers['cache-control'] == 'no-store'
            assert 'sandbox' in response.headers['content-security-policy']
        assert client.get('/api/assistant/inbox?before=1').json() == {'items': [], 'unread': 0}
        changed = {**rt.DEFAULT_PREFERENCES, 'quiet_enabled': True}
        assert client.put('/api/assistant/preferences', json=changed).status_code == 200
        assert client.get('/api/assistant/preferences').json() == changed
        assert client.post('/api/assistant/push/test').status_code == 409
        assert client.get('/api/assistant/reports/missing').status_code == 404


def test_rate_limits_keep_independent_windows(service):
    store = service.store
    assert store.rate_limit('login', 1000, 1, 900)
    assert store.rate_limit('push', 1100, 3, 60)
    assert not store.rate_limit('login', 1101, 1, 900)


def test_open_socket_revoked_with_device(service):
    from starlette.websockets import WebSocketDisconnect
    with remote(service) as client:
        response = login(client, service)
        with client.websocket_connect('wss://search.example.test/api/ws/test', headers={'Origin': service.config.public_origin}) as ws:
            ws.send_text('test')
            assert ws.receive_text() == 'ok'
            client.delete('/api/assistant/devices/' + response.json()['id'], headers=auth_headers())
            with pytest.raises(WebSocketDisconnect) as error:
                ws.receive_text()
            assert error.value.code == 1008


@pytest.mark.asyncio
async def test_queued_run_dispatches_selected_sources_once(service, monkeypatch):
    from api.routes import search
    sources = {'mode': 'local', 'local': {'library_id': 'lib', 'selection': 'documents', 'document_ids': ['doc'], 'model_access': True}}
    with client_for(service) as client:
        plan = create(client, sources=sources)
        response = client.post(f"/api/assistant/schedules/{plan['id']}/run-now", json={'version': 1}, headers={'Idempotency-Key': 'manual-run-test'})
    captured = []
    async def launch(req, session_id_override=None):
        captured.append(req.model_dump())
        rt.sessions[session_id_override] = {'status': 'running'}
        return {'session_id': session_id_override}
    monkeypatch.setattr(search, 'launch_search_request', launch)
    await service.launch(response.json()['id'])
    await service.launch(response.json()['id'])
    assert len(captured) == 1
    assert captured[0]['sources']['local']['document_ids'] == ['doc']
    assert captured[0]['max_time'] == 300
    assert service.store.one('SELECT status FROM runs')['status'] == 'running'


@pytest.mark.asyncio
async def test_schedule_to_report_and_inbox_end_to_end(service, monkeypatch):
    from api.routes import search, history
    with client_for(service) as client:
        plan = create(client)
        run = client.post(f"/api/assistant/schedules/{plan['id']}/run-now", json={'version': 1}, headers={'Idempotency-Key': 'end-to-end-run'}).json()
        async def launch(req, session_id_override=None):
            rt.sessions[session_id_override] = {'status': 'running'}
            return SimpleNamespace(session_id=session_id_override)
        async def load(sid):
            return {'session_id': sid, 'query': '日报', 'answer': '# 报告\n已完成', 'search_state': {}}
        monkeypatch.setattr(search, 'launch_search_request', launch)
        monkeypatch.setattr(history, 'load_history', load)
        await service.tick()
        sid = service.store.one('SELECT session_id FROM runs WHERE id=?', (run['id'],))['session_id']
        rt.sessions[sid]['status'] = 'completed'
        await service.tick()
        inbox = client.get('/api/assistant/inbox').json()
        assert inbox['unread'] == 1
        notification = inbox['items'][0]
        assert notification['url'].startswith('/m?report=')
        report_id = notification['url'].split('=')[1]
        report = client.get('/api/assistant/reports/' + report_id).json()
        assert report['answer'] == '# 报告\n已完成'
        assert client.post('/api/assistant/inbox/' + notification['id'] + '/read').status_code == 200
        assert client.get('/api/assistant/inbox').json()['unread'] == 0
        assert client.get(f"/api/assistant/schedules/{plan['id']}/runs").json()[0]['report_id'] == report_id


@pytest.mark.asyncio
async def test_local_plan_time_limit_cancels_work(service, monkeypatch, tmp_path):
    from api.routes import local_search
    class SlowService:
        async def answer(self, *args, **kwargs):
            await asyncio.sleep(10)
    monkeypatch.setattr(local_search, 'sessions', rt.sessions)
    monkeypatch.setattr(local_search, 'WORKSPACE_ROOT', str(tmp_path / 'workspaces'))
    monkeypatch.setattr(local_search, '_service', lambda: SlowService())
    await local_search.launch_local_search(session_id='timeout-test', query='test', library_id='lib', document_ids=['doc'], history=None, max_time=0.01)
    await rt.sessions['timeout-test']['task']
    assert rt.sessions['timeout-test']['status'] == 'error'
    assert '时间上限' in rt.sessions['timeout-test']['error']
