from __future__ import annotations

import asyncio
import fcntl
import json
import logging
import os
import time
import uuid
from pathlib import Path
from urllib.parse import urlencode

from api.deps import WORKSPACE_ROOT, sessions
from .auth import Config, ensure_admin_secret
from .push import PushSender
from .scheduling import in_quiet_hours, next_occurrence
from .store import Store, encode

logger = logging.getLogger(__name__)
DEFAULT_PREFERENCES = {"completed": True, "errors": True, "quiet_enabled": False, "quiet_start": "22:00", "quiet_end": "08:00", "timezone": "Asia/Shanghai"}


class AssistantRuntime:
    def __init__(self, config: Config):
        self.config = config
        self.store = Store(config.root)
        ensure_admin_secret(config)
        self.push = PushSender(config)
        self.tasks = []
        self.lock = None
        self.last_tick = 0.0
        self.leader = False
        self.started_at = time.time()
        self.started_monotonic = time.monotonic()
        self.instance_id = uuid.uuid4().hex
        self.tick_failed = False

    def health(self):
        now = time.time()
        scheduler_ok = (self.leader and bool(self.tasks) and not self.tasks[0].done()
                        and not self.tick_failed and 0 <= now - self.last_tick <= 15)
        return {
            "scheduler_running": scheduler_ok, "last_tick": self.last_tick,
            "server_time": now, "started_at": self.started_at,
            "uptime_seconds": max(0, int(time.monotonic() - self.started_monotonic)),
            "instance_id": self.instance_id,
            "service_mode": "managed" if os.getenv("SF_SERVICE_MANAGED") == "launchd" else "manual",
            "keep_awake": "ac" if os.getenv("SF_SERVICE_KEEP_AWAKE") == "ac" else "off",
            "catchup_window_minutes": 60,
            "push_ready": self.push.ready, "push_reason": self.push.reason,
        }

    def preferences(self, device_id):
        row = self.store.one("SELECT payload FROM preferences WHERE device_id=?", (device_id,))
        return {**DEFAULT_PREFERENCES, **(json.loads(row["payload"]) if row else {})}

    def track_session(self, session_id: str, payload=None, run_id=None):
        runtime = sessions.get(session_id)
        if not runtime:
            return
        key = runtime.setdefault("assistant_run_id", run_id or uuid.uuid4().hex)
        now = time.time()
        self.store.execute("INSERT OR IGNORE INTO runs(id,session_id,status,payload,created,updated) VALUES(?,?,?,?,?,?)", (key, session_id, "running", encode(payload or {}), now, now))

    async def before_replace(self, session_id):
        current = sessions.get(session_id)
        if current and current.get("status") != "running":
            self.track_session(session_id)
            row = self.store.one("SELECT * FROM runs WHERE id=? AND status='running'", (current["assistant_run_id"],))
            if row:
                await self.finish(row, current["status"], current.get("error") or "")

    async def start(self):
        self.lock = (self.config.root / "worker.lock").open("a+")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close()
            self.lock = None
            # Multiple API workers have separate engine registries; fail instead of
            # silently losing progress or delivering incorrect interrupted reports.
            raise RuntimeError("SearchOS assistant requires one API worker per data directory")
        self.leader = True
        self.store.execute("UPDATE outbox SET status='pending' WHERE status='sending'")
        # Never blindly rerun work after a crash: the model may already have charged.
        for row in self.store.rows("SELECT * FROM runs WHERE status IN ('queued','running')"):
            await self.recover_run(row)
        self.tasks = [asyncio.create_task(self.loop()), asyncio.create_task(self.push_loop())]

    async def stop(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks = []
        if self.lock:
            fcntl.flock(self.lock, fcntl.LOCK_UN)
            self.lock.close()
            self.lock = None
        self.leader = False

    async def recover_run(self, row):
        if row["status"] == "queued" and not row["session_id"]:
            return
        if row["session_id"] in sessions:
            return
        # A committed result can be reconciled once; a partial execution is not restarted.
        result = Path(WORKSPACE_ROOT) / (row["session_id"] or "_none") / "output" / "result.json"
        if row["session_id"] and result.is_file() and result.stat().st_mtime >= row["created"]:
            await self.finish(row, "completed")
        else:
            await self.finish(row, "interrupted", "服务重启，执行已中断；请确认后手动重试。")

    async def loop(self):
        while True:
            try:
                await self.tick()
                self.tick_failed = False
            except Exception:
                self.tick_failed = True
                logger.exception("Assistant scheduler tick failed")
            await asyncio.sleep(2)

    async def tick(self, now=None):
        now = time.time() if now is None else now
        self.last_tick = now
        for sid in list(sessions):
            self.track_session(sid)
        for row in self.store.rows("SELECT * FROM runs WHERE status='running'"):
            current = sessions.get(row["session_id"])
            if current and current.get("assistant_run_id") == row["id"] and current["status"] != "running":
                await self.finish(row, current["status"], current.get("error") or "")
        for schedule in self.store.rows("SELECT * FROM schedules WHERE active=1 AND deleted=0 AND next_run<=? ORDER BY next_run", (now,)):
            busy = any(value.get("status") == "running" for value in sessions.values())
            payload = json.loads(schedule["payload"])
            overdue = now - schedule["next_run"] > 3600
            if busy and not overdue:
                continue
            with self.store.transaction() as db:
                # Recheck version/status under the write lock: pause/edit wins if committed first.
                current = db.execute("SELECT * FROM schedules WHERE id=? AND version=? AND active=1 AND next_run=? AND deleted=0", (schedule["id"], schedule["version"], schedule["next_run"])).fetchone()
                if not current:
                    continue
                key = uuid.uuid4().hex
                slot = str(int(schedule["next_run"]))
                next_run = next_occurrence(payload, now)
                db.execute("UPDATE schedules SET next_run=?,active=?,updated=? WHERE id=?", (next_run, int(next_run is not None), now, schedule["id"]))
                inserted = db.execute("INSERT OR IGNORE INTO runs(id,schedule_id,slot,status,payload,created,updated,error) VALUES(?,?,?,?,?,?,?,?)", (key, schedule["id"], slot, "skipped" if overdue else "queued", encode(payload), now, now, "超过一小时补跑窗口，已跳过" if overdue else "")).rowcount
            if inserted and not overdue:
                await self.launch(key)
            elif inserted:
                await self.finish(self.store.one("SELECT * FROM runs WHERE id=?", (key,)), "skipped", "超过一小时补跑窗口，已跳过")
        # Explicit run-now commands queue durably; at most one scheduled search runs at once.
        if not any(value.get("status") == "running" for value in sessions.values()):
            row = self.store.one("SELECT * FROM runs WHERE status='queued' ORDER BY created LIMIT 1")
            if row:
                await self.launch(row["id"])

    async def launch(self, run_id):
        from api.research.contracts import SearchRequest
        from api.routes.search import launch_search_request
        from searchos.socm.storage.workspace import new_session_id
        with self.store.transaction() as db:
            row = db.execute("SELECT * FROM runs WHERE id=? AND status='queued'", (run_id,)).fetchone()
            if not row:
                return
            session_id = row["session_id"] or new_session_id()
            db.execute("UPDATE runs SET status='running',session_id=?,updated=? WHERE id=?", (session_id, time.time(), run_id))
            payload = json.loads(row["payload"])
        try:
            response = await launch_search_request(SearchRequest(query=payload["instruction"], effort=payload.get("effort", "medium"), max_time=payload.get("max_time", 300), sources=payload.get("sources")), session_id_override=session_id)
            sid = response["session_id"] if isinstance(response, dict) else response.session_id
            runtime = sessions[sid]
            runtime["assistant_run_id"] = run_id
        except Exception as exc:
            row = self.store.one("SELECT * FROM runs WHERE id=?", (run_id,))
            await self.finish(row, "error", str(getattr(exc, "detail", exc)))

    async def finish(self, run: dict, status: str, error=""):
        from api.routes.history import load_history
        now = time.time()
        report = None
        report_id = uuid.uuid4().hex if status == "completed" else None
        if report_id:
            try:
                report = await load_history(run["session_id"])
                # Reports are immutable snapshots; do not persist unbounded execution traces.
                report = {key: report.get(key) for key in ("session_id", "query", "answer", "search_state", "coverage_score", "evidence_count")}
            except Exception:
                status, error, report_id = "error", "任务已结束，但报告快照暂不可读取。请查看原任务。", None
        event_id = uuid.uuid4().hex
        kind = "completed" if status == "completed" else "error"
        url = "/m?" + urlencode({"report": report_id} if report_id else {"session": run["session_id"]}) if run["session_id"] else "/m?" + urlencode({"view": "tasks", **({"plan": run["schedule_id"]} if run["schedule_id"] else {})})
        payload = json.loads(run["payload"])
        title = payload.get("title") or payload.get("query") or (report or {}).get("query") or "SearchOS 任务"
        with self.store.transaction() as db:
            if db.execute("SELECT id FROM notifications WHERE run_id=?", (run["id"],)).fetchone():
                return
            db.execute("UPDATE runs SET status=?,updated=?,error=?,report_id=? WHERE id=?", (status, now, error[:2000], report_id, run["id"]))
            if report_id:
                db.execute("INSERT INTO reports VALUES(?,?,?,?,?)", (report_id, run["id"], run["session_id"], encode(report), now))
            db.execute("INSERT INTO notifications(id,run_id,kind,title,body,url,created) VALUES(?,?,?,?,?,?,?)", (event_id, run["id"], kind, title[:120], "报告已生成" if report_id else error[:300] or "任务未能完成", url, now))
            for subscription in db.execute("SELECT id FROM subscriptions").fetchall():
                db.execute("INSERT OR IGNORE INTO outbox(id,notification_id,subscription_id,status,next_try) VALUES(?,?,?,'pending',?)", (uuid.uuid4().hex, event_id, subscription["id"], now))

    async def push_loop(self):
        while True:
            try:
                await self.deliver_push()
            except Exception:
                logger.exception("Assistant notification worker failed")
            await asyncio.sleep(3)

    async def deliver_push(self, now=None):
        if not self.push.ready:
            return
        now = time.time() if now is None else now
        row = self.store.one("SELECT * FROM outbox WHERE status='pending' AND next_try<=? ORDER BY next_try LIMIT 1", (now,))
        if not row:
            return
        subscription = self.store.one("SELECT * FROM subscriptions WHERE id=?", (row["subscription_id"],))
        notification = self.store.one("SELECT * FROM notifications WHERE id=?", (row["notification_id"],))
        if not subscription or not notification:
            self.store.execute("UPDATE outbox SET status='cancelled' WHERE id=?", (row["id"],))
            return
        device = self.store.one("SELECT id FROM devices WHERE id=? AND revoked IS NULL AND expires>?", (subscription["device_id"], now))
        prefs = self.preferences(subscription["device_id"])
        if not device or not prefs["completed" if notification["kind"] == "completed" else "errors"]:
            self.store.execute("UPDATE outbox SET status='cancelled' WHERE id=?", (row["id"],))
            return
        if in_quiet_hours(prefs, now):
            self.store.execute("UPDATE outbox SET next_try=? WHERE id=?", (now + 60, row["id"]))
            return
        self.store.execute("UPDATE outbox SET status='sending' WHERE id=?", (row["id"],))
        try:
            result = await asyncio.to_thread(self.push.send, json.loads(subscription["payload"]), notification)
            self.store.execute("UPDATE outbox SET status=?,attempts=attempts+1,error='' WHERE id=?", ("sent" if result == "sent" else "expired", row["id"]))
            if result == "gone":
                self.store.execute("DELETE FROM subscriptions WHERE id=?", (subscription["id"],))
        except Exception:
            attempts = row["attempts"] + 1
            self.store.execute("UPDATE outbox SET status=?,attempts=?,next_try=?,error=? WHERE id=?", ("failed" if attempts >= 5 else "pending", attempts, now + min(3600, 30 * 2 ** attempts), "推送投递失败", row["id"]))


_runtime: AssistantRuntime | None = None


def get_runtime() -> AssistantRuntime:
    global _runtime
    if _runtime is None:
        _runtime = AssistantRuntime(Config.from_env())
    return _runtime
