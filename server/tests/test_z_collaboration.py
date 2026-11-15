import json
import threading
import sys
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from requirement_platform.main import app
from requirement_platform.db import SessionLocal
from requirement_platform.models import BackgroundJob, Requirement, User, utcnow
from requirement_platform.collaboration_models import Conversation, EmailDelivery, EmailSubscription
from requirement_platform.security import create_token, hash_password
from requirement_platform.domain.common import audit
from requirement_platform import dsh, notifications, conversations
from requirement_platform.notifications import claim_email, send_email, subscription_token
from requirement_platform.worker import claim_job, run_job


def actor(role="viewer"):
    with SessionLocal() as db:
        suffix = uuid4().hex
        row = User(username=suffix, email=f"{suffix}@example.com", password_hash=hash_password("password123"), role=role)
        db.add(row); db.commit()
        return {"Authorization": f"Bearer {create_token(row)}"}


def create(client, headers=None, **kwargs):
    result = client.post("/api/requirements", headers=headers or {}, json={"type": "feature", "title": "讨论并完善行影集", "description": "希望能够在需求提交后与开发者继续讨论详细使用场景。", **kwargs})
    assert result.status_code == 200, result.text
    return result.json()["data"]


def test_submit_is_immediate_and_conversation_is_private(monkeypatch):
    with TestClient(app) as client:
        # Creation must never call Harness in the request path.
        monkeypatch.setattr(dsh, "run_harness", lambda *a, **kw: pytest.fail("AI blocked submission"))
        row = create(client, actor("admin"))
        anonymous = create(client)
        receipt = {"X-Requirement-Edit-Token": anonymous["edit_token"]}
        url = f"/api/requirements/{anonymous['reference'] if 'reference' in anonymous else anonymous['id']}/conversation"
        assert client.get(url).status_code == 403
        assert client.get(url, headers=actor()).status_code == 403
        assert client.get(url, headers=receipt).status_code == 200
        payload = {"client_id": uuid4().hex, "content": "我想补充一个手机上遇到的问题。"}
        sent = client.post(url, headers=receipt, json=payload)
        assert sent.status_code == 200, sent.text
        assert client.post(url, headers=receipt, json=payload).json()["data"]["id"] == sent.json()["data"]["id"]
        assert client.post(url, headers=receipt, json={**payload, "mode": "repair"}).status_code == 403
        assert client.post(url, headers=receipt, json={**payload, "client_id": uuid4().hex}).status_code == 409
        with SessionLocal() as db:
            job = db.query(BackgroundJob).filter_by(job_type="conversation", object_id=sent.json()["data"]["id"]).one()
            job_id = job.id
        monkeypatch.setattr(conversations, "resolve_model_targets", lambda *_: [SimpleNamespace()])
        monkeypatch.setattr(dsh, "run_harness", lambda *a, **kw: "可以描述一下手机型号和操作步骤吗？")
        run_job(job_id)
        messages = client.get(url, headers=receipt).json()["data"]["messages"]
        assert messages[0]["response"] == "可以描述一下手机型号和操作步骤吗？"
        assert messages[0]["status"] == "completed"
        with SessionLocal() as db:
            assert db.get(Requirement, anonymous["id"]).description == anonymous["description"]


def test_failure_retry_and_admin_modes(monkeypatch):
    with TestClient(app) as client:
        admin = actor("admin")
        row = create(client, admin)
        url = f"/api/requirements/{row['id']}/conversation"
        sent = client.post(url, headers=admin, json={"client_id": uuid4().hex, "content": "请提出修复补丁", "mode": "repair"}).json()["data"]
        monkeypatch.setattr(conversations, "resolve_model_targets", lambda *_: [])
        with SessionLocal() as db:
            job = db.query(BackgroundJob).filter_by(object_id=sent["id"], job_type="conversation").one()
            job.attempts = 5; db.commit(); job_id = job.id
        run_job(job_id)
        assert client.get(url, headers=admin).json()["data"]["messages"][0]["status"] == "failed"
        assert client.post(url + f"/{sent['id']}/retry", headers=admin).status_code == 429
        from requirement_platform.collaboration_models import AIQuota
        from datetime import timedelta
        with SessionLocal() as db:
            db.query(AIQuota).filter(AIQuota.key.like('pace:%')).update({"expires_at": utcnow() - timedelta(seconds=1)})
            db.commit()
        assert client.post(url + f"/{sent['id']}/retry", headers=admin).status_code == 200
        assert client.post(url + f"/{sent['id']}/retry", headers=admin).status_code == 409


def test_email_verification_transaction_retry_and_unsubscribe(monkeypatch):
    with TestClient(app) as client:
        admin = actor("admin")
        row = create(client, admin, notification_email=f"{uuid4().hex}@example.com", notification_opt_in=True)
        with SessionLocal() as db:
            sub = db.query(EmailSubscription).filter_by(requirement_id=row["id"]).one()
            sub_id = sub.id
            verification = db.query(EmailDelivery).filter_by(subscription_id=sub_id).one()
            assert verification.kind == "verify"
            audit(db, None, "requirement.status_changed", "requirement", row["id"], after="candidate")
            db.commit()
            assert db.query(EmailDelivery).filter_by(subscription_id=sub_id).count() == 1
        token = subscription_token(sub_id, "verify")
        assert client.post("/api/notifications/verify", json={"token": token}).status_code == 200
        assert client.post("/api/notifications/unsubscribe", json={"token": token}).status_code == 400
        with SessionLocal() as db:
            audit(db, None, "requirement.status_changed", "requirement", row["id"], after="candidate")
            db.rollback()
            assert db.query(EmailDelivery).filter_by(subscription_id=sub_id).count() == 1
            audit(db, None, "requirement.status_changed", "requirement", row["id"], after="release_ready")
            db.commit()
            mail = db.query(EmailDelivery).filter_by(subscription_id=sub_id, kind="completed").one()
            assert row["description"] not in mail.body
            mail.status, mail.attempts, mail.lease_token = "sending", 5, "test-lease"
            db.commit(); mail_id = mail.id
            monkeypatch.setattr(notifications, "settings", replace(notifications.settings, smtp_host=""))
            send_email(db, mail_id, "test-lease")
            db.expire_all()
            assert db.get(EmailDelivery, mail_id).status == "failed"
        assert client.get("/api/admin/notifications").status_code == 401
        assert client.post(f"/api/admin/notifications/{mail_id}/retry", headers=admin).status_code == 200
        assert client.post("/api/notifications/unsubscribe", json={"token": subscription_token(sub_id, "unsubscribe")}).status_code == 200
        with SessionLocal() as db:
            mail = db.get(EmailDelivery, mail_id)
            mail.status, mail.lease_token = "sending", "after-unsubscribe"
            db.commit()
            send_email(db, mail_id, "after-unsubscribe")
            db.expire_all()
            assert db.get(EmailDelivery, mail_id).status == "cancelled"


def test_consultation_is_delivered_to_submitters_private_conversation():
    with TestClient(app) as client:
        row = create(client)
        receipt = {"X-Requirement-Edit-Token": row["edit_token"]}
        url = f"/api/requirements/{row['id']}"
        assert client.post(url + "/consultations", headers=receipt, json={"body": "请提供复现步骤"}).status_code == 401
        assert client.post(url + "/consultations", headers=actor("admin"), json={"body": "请提供复现步骤"}).status_code == 200
        assert client.get(url + "/conversation", headers=receipt).json()["data"]["messages"][0]["response"] == "请提供复现步骤"


def test_smtp_success_is_fenced_and_old_discussion_link_is_revoked(monkeypatch):
    from requirement_platform.notifications import subscribe
    sent = []
    class SMTP:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def send_message(self, message): sent.append(message)
    monkeypatch.setattr(notifications.smtplib, "SMTP", SMTP)
    monkeypatch.setattr(notifications, "settings", replace(notifications.settings, smtp_host="mock-only", smtp_from="test@example.com", smtp_tls="none", smtp_username=""))
    with TestClient(app) as client:
        row = create(client, notification_email=f"{uuid4().hex}@example.com", notification_opt_in=True)
        receipt = {"X-Requirement-Edit-Token": row["edit_token"]}
        with SessionLocal() as db:
            sub = db.query(EmailSubscription).filter_by(requirement_id=row['id']).one()
            sub.verified = True
            mail = db.query(EmailDelivery).filter_by(subscription_id=sub.id).one()
            mail.status, mail.lease_token = 'sending', 'current-lease'
            db.commit()
            send_email(db, mail.id, 'stale-lease')
            assert not sent
            send_email(db, mail.id, 'current-lease')
            db.expire_all()
            assert db.get(EmailDelivery, mail.id).status == 'sent' and len(sent) == 1
            sub_id, address = sub.id, sub.email
        old = subscription_token(sub_id, 'conversation')
        url = f"/api/requirements/{row['id']}/conversation"
        assert client.get(url, headers={'X-Requirement-Edit-Token':old}).status_code == 200
        assert client.post('/api/notifications/unsubscribe', json={'token':subscription_token(sub_id,'unsubscribe')}).status_code == 200
        assert client.get(url, headers={'X-Requirement-Edit-Token':old}).status_code == 403
        assert client.post(f"/api/requirements/{row['id']}/notifications",headers=receipt,json={'email':address}).status_code == 200
        assert client.post('/api/notifications/verify',json={'token':subscription_token(sub_id,'verify')}).status_code == 200
        assert client.get(url, headers={'X-Requirement-Edit-Token':old}).status_code == 403


@pytest.mark.skipif(sys.platform == "win32", reason="Official 0.2.2rc2 Windows wheel fails loading its native binding; exercised in Linux image/CI")
def test_official_sdk_runs_with_no_tools_or_telemetry(tmp_path, monkeypatch):
    from requirement_platform.db import init_db
    init_db()
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append(payload)
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            events = [
                ("message_start", {"type": "message_start", "message": {"id": "test", "type": "message", "role": "assistant", "model": "deepseek-chat", "content": [], "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 0}}}),
                ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
                ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "SDK 已连接"}}),
                ("content_block_stop", {"type": "content_block_stop", "index": 0}),
                ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": 5}}),
                ("message_stop", {"type": "message_stop"}),
            ]
            for name, chunk in events:
                self.wfile.write(("event: " + name + "\ndata: " + json.dumps(chunk) + "\n\n").encode())
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    monkeypatch.setattr(dsh, "settings", replace(dsh.settings, dsh_home=str(tmp_path), dsh_enabled=True))
    target = SimpleNamespace(model_name="deepseek-chat", api_key="test-only", api_base=f"http://127.0.0.1:{server.server_port}/v1", timeout_seconds=15, reasoning_effort="none")
    try:
        try:
            result = dsh.run_harness(target, json.dumps({"message": "测试对话"}))
        except RuntimeError:
            pytest.fail(f"Harness did not complete; model requests: {requests}")
        assert result == "SDK 已连接"
        assert requests
        assert '只处理行影集' in json.dumps(requests[0], ensure_ascii=False)
        assert requests[0]['max_tokens'] <= 4096
        assert requests[0]['thinking'] == {'type': 'disabled'}
        assert not requests[0].get("tools"), requests[0].get("tools")
        assert 'session_log' not in json.dumps(requests[0]).lower()
    finally:
        server.shutdown(); server.server_close()


@pytest.mark.parametrize('effort,expected', [('none','off'), ('minimal','low'), ('medium','low'), ('high','high'), ('xhigh','max')])
def test_harness_honors_configured_reasoning_budget(tmp_path, monkeypatch, effort, expected):
    from contextlib import nullcontext
    import deepseek_harness
    calls = []
    class Harness:
        def __init__(self, **kwargs): calls.append(kwargs)
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def run(self, *_args, **_kwargs):
            return SimpleNamespace(finish_reason='completed', final_response='需要提供行影集版本。')
    monkeypatch.setattr(deepseek_harness, 'DeepSeekHarness', Harness)
    monkeypatch.setattr(dsh, 'bounded_endpoint', lambda _: nullcontext('http://127.0.0.1:1'))
    monkeypatch.setattr(dsh, 'settings', replace(dsh.settings, dsh_home=str(tmp_path)))
    target = SimpleNamespace(model_name='deepseek-v4.1-flash', timeout_seconds=45, reasoning_effort=effort)
    assert dsh.run_harness(target, '{}') == '需要提供行影集版本。'
    assert calls[0]['reasoning_effort'] == expected
    assert calls[0]['api_key'] == 'local-gateway'


def test_triage_uses_compact_schema_with_valid_defaults(monkeypatch):
    prompts = []
    def run(_target, prompt):
        prompts.append(json.loads(prompt))
        return json.dumps({'requirement_revision': 1, 'problem_summary': '行影集导出失败', 'category': 'bug',
                           'recommended_disposition': 'clarify', 'generated_at': '2026-11-15T00:00:00Z'})
    monkeypatch.setattr(dsh, 'run_harness', run)
    result = dsh.triage_with_harness({'content_revision': 1}, [], None)
    assert result['blocking_questions'] == []
    assert result['fallback_reason'] is None
    assert 'value_assessment' not in prompts[0]['schema']['properties']
    assert set(prompts[0]['schema']['required']) <= prompts[0]['schema']['properties'].keys()
