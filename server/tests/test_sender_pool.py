from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from requirement_platform.collaboration_models import EmailDelivery, EmailSubscription, MailSettings
from requirement_platform.db import SessionLocal
from requirement_platform.main import app
from requirement_platform import notifications
from test_z_collaboration import actor, create


@pytest.fixture
def pool():
    with TestClient(app):
        with SessionLocal() as db: db.query(MailSettings).delete(); db.commit()
        yield
        with SessionLocal() as db: db.query(MailSettings).delete(); db.commit()


def account(name):
    return dict(name=name, host=f"{name}.example.com", port=465, username=f"{name}@example.com", password="private-authorization-code", sender=f"{name}@example.com", tls="ssl", enabled=True, daily_limit=100)


def test_settings_manager_only_encrypted_and_preserved(pool):
    with TestClient(app) as client:
        assert client.get('/api/admin/mail-settings').status_code == 401
        assert client.put('/api/admin/mail-settings', headers=actor(), json={"accounts": []}).status_code == 403
        headers = actor("admin")
        response = client.put('/api/admin/mail-settings', headers=headers, json={"accounts": [account("a"), account("b")]})
        assert response.status_code == 200, response.text
        assert "private-authorization-code" not in response.text
        safe = response.json()["data"]["accounts"]
        assert safe[0]["has_password"]
        with SessionLocal() as db:
            encrypted = db.get(MailSettings, 1).accounts[0]["password_encrypted"]
            assert "private-authorization-code" not in encrypted
        changed = [{k: v for k, v in a.items() if k not in {"has_password", "used_today"}} for a in safe]
        changed[0]["name"] = "Changed"
        assert client.put('/api/admin/mail-settings', headers=headers, json={"accounts": changed}).status_code == 200
        with SessionLocal() as db: assert db.get(MailSettings, 1).accounts[0]["password_encrypted"] == encrypted


def test_rotate_failover_all_failed_and_account_limits(pool, monkeypatch):
    tried, sent = [], []
    failing = set()
    class SMTP:
        def __init__(self, host, *args, **kwargs):
            tried.append(host); self.host = host
            if host in failing: raise OSError("provider-secret-diagnostic")
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def login(self, *args): pass
        def send_message(self, message): sent.append((self.host, message["Message-ID"]))
    monkeypatch.setattr(notifications.smtplib, "SMTP_SSL", SMTP)
    with TestClient(app) as client:
        headers = actor("admin")
        assert client.put('/api/admin/mail-settings', headers=headers, json={"accounts": [account("a"), account("b"), {**account("disabled"), "enabled": False}]}).status_code == 200
        requirement = create(client, headers)
        with SessionLocal() as db:
            sub = EmailSubscription(requirement_id=requirement["id"], email=f"{uuid4().hex}@example.com", verified=True)
            db.add(sub); db.flush()
            def deliver(attempts=1):
                row = EmailDelivery(subscription_id=sub.id, event_key=uuid4().hex, kind="changed", subject="test", body="test", status="sending", attempts=attempts, lease_token="test")
                db.add(row); db.commit(); row_id = row.id
                notifications.send_email(db, row_id, "test")
                db.expire_all()
                return db.get(EmailDelivery, row_id)
            assert deliver().status == "sent"
            assert deliver().status == "sent"
            assert tried == ["a.example.com", "b.example.com"]
            failing.add("a.example.com")
            assert deliver().status == "sent"
            assert tried[-2:] == ["a.example.com", "b.example.com"]
            failing.add("b.example.com")
            row = deliver(attempts=notifications.settings.max_job_attempts)
            assert row.status == "failed"
            assert tried[-2:] == ["b.example.com", "a.example.com"]
            assert "provider-secret" not in row.last_error
            assert not any("disabled" in host for host in tried)
        safe = client.get('/api/admin/mail-settings', headers=headers).json()["data"]["accounts"]
        assert safe[0]["used_today"] == 3
        assert safe[1]["used_today"] == 3
