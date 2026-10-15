from __future__ import annotations

import hmac
import json
import secrets
import time
import uuid
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator

from .auth import COOKIE, digest, ensure_admin_secret
from .push import validate_subscription
from .runtime import get_runtime
from .scheduling import ScheduleInput, next_occurrence
from .store import encode

router = APIRouter(prefix="/api/assistant", tags=["mobile assistant"])


def who(request: Request):
    device = getattr(request.state, "assistant_device", None)
    if not device:
        raise HTTPException(401, "请先绑定设备")
    return device


def admin(request: Request):
    device = who(request)
    if not device["admin"]:
        raise HTTPException(403, "请在管理员设备上操作")
    return device


def schedule_view(row):
    return {**json.loads(row["payload"]), "id": row["id"], "version": row["version"], "active": bool(row["active"]), "next_run": row["next_run"], "updated": row["updated"]}


@router.get("/access")
def access(request: Request):
    runtime = get_runtime()
    device = getattr(request.state, "assistant_device", None)
    return {"remote": runtime.config.remote, "authenticated": bool(device), "device": {key: device[key] for key in ("id", "name", "admin")} if device else None, "origin": runtime.config.public_origin or None}


class Login(BaseModel):
    token: str = Field(min_length=1, max_length=200)
    name: str = Field(default="管理员设备", min_length=1, max_length=80)


class Claim(BaseModel):
    code: str = Field(pattern=r"^\d{8}$")
    name: str = Field(default="我的 iPhone", min_length=1, max_length=80)


def issue_device(response: Response, name: str, is_admin: bool, db):
    token = secrets.token_urlsafe(36)
    device_id, now = uuid.uuid4().hex, time.time()
    expires = now + 30 * 86400
    db.execute("INSERT INTO devices(id,name,token_hash,admin,created,last_seen,expires) VALUES(?,?,?,?,?,?,?)", (device_id, name.strip(), digest(token), int(is_admin), now, now, expires))
    response.set_cookie(COOKIE, token, max_age=30 * 86400, httponly=True, secure=True, samesite="strict", path="/")
    return {"id": device_id, "name": name, "admin": is_admin, "expires": expires}


@router.post("/login")
def login(body: Login, response: Response):
    runtime = get_runtime()
    if not runtime.config.remote:
        raise HTTPException(409, "本机模式无需登录")
    if not runtime.store.rate_limit("admin-login", time.time(), 5, 900):
        raise HTTPException(429, "尝试过于频繁，请稍后再试")
    secret = ensure_admin_secret(runtime.config).read_text().strip()
    if not hmac.compare_digest(digest(body.token), digest(secret)):
        raise HTTPException(401, "管理员凭据不正确")
    with runtime.store.transaction() as db:
        return issue_device(response, body.name, True, db)


@router.post("/pairings")
def create_pairing(request: Request):
    admin(request)
    runtime = get_runtime()
    now = time.time()
    if not runtime.config.remote:
        raise HTTPException(409, "请先配置 SF_PUBLIC_ORIGIN，再通过 HTTPS 管理员入口绑定手机")
    if not runtime.store.rate_limit("pairing-create", now, 10):
        raise HTTPException(429, "请稍后再生成配对码")
    code = f"{secrets.randbelow(100000000):08d}"
    key = uuid.uuid4().hex
    runtime.store.execute("INSERT INTO pairings(id,code_hash,expires,created) VALUES(?,?,?,?)", (key, digest(code), now + 300, now))
    return {"id": key, "code": code, "expires": now + 300, "url": runtime.config.public_origin + "/m"}


@router.post("/pairings/claim")
def claim_pairing(body: Claim, response: Response):
    runtime = get_runtime()
    now = time.time()
    if not runtime.config.remote:
        raise HTTPException(409, "远程设备绑定尚未配置")
    if not runtime.store.rate_limit("pairing-claim", now, 10, 900):
        raise HTTPException(429, "配对尝试过于频繁，请稍后再试")
    with runtime.store.transaction() as db:
        row = db.execute("SELECT id FROM pairings WHERE code_hash=? AND expires>? AND consumed IS NULL", (digest(body.code), now)).fetchone()
        if not row:
            raise HTTPException(401, "配对码无效、已使用或已过期")
        db.execute("UPDATE pairings SET consumed=? WHERE id=?", (now, row["id"]))
        return issue_device(response, body.name, False, db)


@router.get("/devices")
def devices(request: Request):
    device = who(request)
    runtime = get_runtime()
    rows = runtime.store.rows("SELECT id,name,admin,created,last_seen,expires,revoked FROM devices ORDER BY created DESC") if device["admin"] else runtime.store.rows("SELECT id,name,admin,created,last_seen,expires,revoked FROM devices WHERE id=?", (device["id"],))
    return rows


@router.delete("/devices/{device_id}")
def revoke(device_id: str, request: Request, response: Response):
    device = who(request)
    if not device["admin"] and device["id"] != device_id:
        raise HTTPException(403, "只能撤销当前设备")
    store = get_runtime().store
    with store.transaction() as db:
        db.execute("UPDATE devices SET revoked=? WHERE id=?", (time.time(), device_id))
        db.execute("DELETE FROM subscriptions WHERE device_id=?", (device_id,))
    if device["id"] == device_id:
        response.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="strict")
    return {"ok": True}


@router.post("/logout")
def logout(request: Request, response: Response):
    return revoke(who(request)["id"], request, response)


@router.get("/schedules")
def list_schedules():
    return [schedule_view(row) for row in get_runtime().store.rows("SELECT * FROM schedules WHERE deleted=0 ORDER BY created DESC")]


@router.post("/schedules")
def create_schedule(body: ScheduleInput, request: Request, idempotency_key: str = Header(min_length=8, max_length=128)):
    who(request)
    store = get_runtime().store
    payload = body.model_dump(exclude={"version", "active"})
    now = time.time()
    next_run = next_occurrence(payload, now) if body.active else None
    if body.active and next_run is None:
        raise HTTPException(422, "计划时间已过去或不存在，请调整时间")
    # A stable client UUID makes save retries safe without storing personal data in a key.
    key = digest("schedule:" + idempotency_key)
    with store.transaction() as db:
        existing = db.execute("SELECT * FROM schedules WHERE id=?", (key,)).fetchone()
        if existing:
            if existing["payload"] != encode(payload) or bool(existing["active"]) != body.active or existing["deleted"]:
                raise HTTPException(409, "此保存请求已使用，请刷新后重试")
            return schedule_view(existing)
        db.execute("INSERT INTO schedules(id,version,payload,active,next_run,created,updated) VALUES(?,1,?,?,?,?,?)", (key, encode(payload), int(body.active), next_run, now, now))
    return schedule_view(store.one("SELECT * FROM schedules WHERE id=?", (key,)))


@router.put("/schedules/{schedule_id}")
def edit_schedule(schedule_id: str, body: ScheduleInput):
    store = get_runtime().store
    payload = body.model_dump(exclude={"version", "active"})
    now = time.time()
    next_run = next_occurrence(payload, now) if body.active else None
    if body.active and next_run is None:
        raise HTTPException(422, "计划时间已过去或不存在")
    with store.transaction() as db:
        row = db.execute("SELECT * FROM schedules WHERE id=? AND deleted=0", (schedule_id,)).fetchone()
        if not row:
            raise HTTPException(404, "计划不存在")
        if body.version != row["version"]:
            raise HTTPException(409, "计划已在其他页面更新，请刷新后重新编辑")
        db.execute("UPDATE schedules SET payload=?,active=?,next_run=?,updated=?,version=version+1 WHERE id=?", (encode(payload), int(body.active), next_run, now, schedule_id))
    return schedule_view(store.one("SELECT * FROM schedules WHERE id=?", (schedule_id,)))


class Version(BaseModel):
    version: int


@router.post("/schedules/{schedule_id}/{action}")
def schedule_action(schedule_id: str, action: Literal["pause", "resume", "run-now", "delete"], body: Version, idempotency_key: str | None = Header(default=None)):
    store = get_runtime().store
    now = time.time()
    with store.transaction() as db:
        row = db.execute("SELECT * FROM schedules WHERE id=? AND deleted=0", (schedule_id,)).fetchone()
        if not row:
            raise HTTPException(404, "计划不存在")
        if body.version != row["version"]:
            raise HTTPException(409, "计划版本已变化，请刷新后重试")
        if action == "run-now":
            if not idempotency_key or not 8 <= len(idempotency_key) <= 128:
                raise HTTPException(422, "立即执行需要唯一请求标识")
            slot = "manual:" + digest(idempotency_key)
            existing = db.execute("SELECT * FROM runs WHERE schedule_id=? AND slot=?", (schedule_id, slot)).fetchone()
            if existing:
                return dict(existing)
            if db.execute("SELECT id FROM runs WHERE schedule_id=? AND status IN ('queued','running')", (schedule_id,)).fetchone():
                raise HTTPException(409, "此计划已有任务在等待或执行")
            run_id = uuid.uuid4().hex
            db.execute("INSERT INTO runs(id,schedule_id,slot,status,payload,created,updated) VALUES(?,?,?,'queued',?,?,?)", (run_id, schedule_id, slot, row["payload"], now, now))
            return {"id": run_id, "status": "queued"}
        next_run = next_occurrence(json.loads(row["payload"]), now) if action == "resume" else None
        if action == "resume" and next_run is None:
            raise HTTPException(422, "此计划时间已过，请先编辑")
        db.execute("UPDATE schedules SET active=?,next_run=?,deleted=?,version=version+1,updated=? WHERE id=?", (int(action == "resume"), next_run, int(action == "delete"), now, schedule_id))
        if action == "delete":
            db.execute("UPDATE runs SET status='skipped',error='计划已删除',updated=? WHERE schedule_id=? AND status='queued'", (now, schedule_id))
    return {"ok": True}


@router.get("/schedules/{schedule_id}/runs")
def schedule_runs(schedule_id: str, before: float | None = None):
    return get_runtime().store.rows("SELECT id,session_id,status,created,updated,error,report_id FROM runs WHERE schedule_id=? AND created<? ORDER BY created DESC LIMIT 50", (schedule_id, before or 1e20))


@router.get("/status")
def status():
    return get_runtime().health()


@router.get("/inbox")
def inbox(before: float | None = None):
    store = get_runtime().store
    return {"items": store.rows("SELECT * FROM notifications WHERE created<? ORDER BY created DESC LIMIT 50", (before or 1e20,)), "unread": store.one("SELECT count(*) AS n FROM notifications WHERE read_at IS NULL")["n"]}


@router.post("/inbox/{notification_id}/read")
def mark_read(notification_id: str):
    get_runtime().store.execute("UPDATE notifications SET read_at=COALESCE(read_at,?) WHERE id=?", (time.time(), notification_id))
    return {"ok": True}


@router.get("/reports/{report_id}")
def report(report_id: str):
    row = get_runtime().store.one("SELECT * FROM reports WHERE id=?", (report_id,))
    if not row:
        raise HTTPException(404, "报告不存在")
    return {"id": row["id"], "created": row["created"], **json.loads(row["payload"])}


class Preferences(BaseModel):
    completed: bool = True
    errors: bool = True
    quiet_enabled: bool = False
    quiet_start: str = Field(default="22:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    quiet_end: str = Field(default="08:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    timezone: str = "Asia/Shanghai"

    @field_validator("timezone")
    @classmethod
    def zone(cls, value):
        try:
            ZoneInfo(value)
        except Exception as exc:
            raise ValueError("无效时区") from exc
        return value


@router.get("/preferences")
def get_preferences(request: Request):
    return get_runtime().preferences(who(request)["id"])


@router.put("/preferences")
def save_preferences(body: Preferences, request: Request):
    get_runtime().store.execute("INSERT INTO preferences VALUES(?,?) ON CONFLICT(device_id) DO UPDATE SET payload=excluded.payload", (who(request)["id"], encode(body.model_dump())))
    return body.model_dump()


@router.get("/push/config")
def push_config(request: Request):
    runtime = get_runtime()
    device = who(request)
    return {"ready": runtime.push.ready, "reason": runtime.push.reason, "public_key": runtime.push.public_key, "subscriptions": runtime.store.rows("SELECT id,created FROM subscriptions WHERE device_id=?", (device["id"],)), "deliveries": runtime.store.rows("SELECT o.status,o.attempts,o.error FROM outbox o JOIN subscriptions s ON s.id=o.subscription_id WHERE s.device_id=? ORDER BY o.next_try DESC LIMIT 10", (device["id"],))}


@router.post("/push/subscriptions")
def subscribe(body: dict, request: Request):
    runtime = get_runtime()
    device = who(request)
    if not runtime.push.ready:
        raise HTTPException(409, runtime.push.reason)
    try:
        payload = validate_subscription(body)
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    endpoint_hash = digest(payload["endpoint"])
    with runtime.store.transaction() as db:
        existing = db.execute("SELECT id,device_id FROM subscriptions WHERE endpoint_hash=?", (endpoint_hash,)).fetchone()
        if existing and existing["device_id"] != device["id"]:
            raise HTTPException(409, "该浏览器订阅已绑定另一设备，请先关闭旧订阅")
        key = existing["id"] if existing else uuid.uuid4().hex
        db.execute("INSERT INTO subscriptions VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload", (key, device["id"], endpoint_hash, encode(payload), time.time()))
    return {"id": key}


@router.delete("/push/subscriptions")
def unsubscribe(request: Request):
    get_runtime().store.execute("DELETE FROM subscriptions WHERE device_id=?", (who(request)["id"],))
    return {"ok": True}


@router.post("/push/test")
def push_test(request: Request):
    runtime = get_runtime()
    device = who(request)
    if not runtime.push.ready:
        raise HTTPException(409, runtime.push.reason)
    now = time.time()
    if not runtime.store.rate_limit("push-test:" + device["id"], now, 3, 60):
        raise HTTPException(429, "请稍后再测试")
    rows = runtime.store.rows("SELECT id FROM subscriptions WHERE device_id=?", (device["id"],))
    if not rows:
        raise HTTPException(409, "当前设备尚未订阅推送")
    key = uuid.uuid4().hex
    with runtime.store.transaction() as db:
        db.execute("INSERT INTO notifications(id,kind,title,body,url,created) VALUES(?,?,?,?,?,?)", (key, "completed", "通知测试", "这是一条主动发送的测试提醒", "/m?view=inbox", now))
        for row in rows:
            db.execute("INSERT INTO outbox(id,notification_id,subscription_id,status,next_try) VALUES(?,?,?,'pending',?)", (uuid.uuid4().hex, key, row["id"], now))
    return {"queued": True, "notification_id": key}
