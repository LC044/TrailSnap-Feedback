import base64
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from requirement_platform import dsh
from requirement_platform.api import ai_overview, intake
from requirement_platform.collaboration_models import AIChatActivity, ModelRequestUsage
from requirement_platform.conversation_usage import record_chat
from requirement_platform.db import SessionLocal
from requirement_platform.main import app
from test_z_collaboration import actor


def test_overview_separates_admissions_retries_and_model_attempts(monkeypatch):
    # Fixed to a day outside the dates used by other tests in the shared DB.
    now = datetime(2034, 3, 4, 8, tzinfo=timezone.utc)
    monkeypatch.setattr(ai_overview, "utcnow", lambda: now)
    c1, c2 = str(uuid4()), str(uuid4())
    with TestClient(app) as client:
        with SessionLocal() as db:
            record_chat(db, "requirement", c1, "user:one")
            record_chat(db, "requirement", c1, "user:one", retry=True)
            record_chat(db, "intake", c2, "user:one")
            record_chat(db, "intake", str(uuid4()), "intake:anonymous")
            for row in db.new:
                assert isinstance(row, AIChatActivity)
                row.created_at = now
                assert row.actor_key not in {"user:one", "intake:anonymous"}
            opts = dict(connection_id="overview", connection_name="Provider", model_id="model", model_name="Example", reserved_tokens=35, created_at=now)
            db.add_all([ModelRequestUsage(**opts, conversation_kind="intake", status="completed", input_tokens=15, output_tokens=2),
                        ModelRequestUsage(**opts, conversation_kind="intake", status="failed"), ModelRequestUsage(**opts, status="completed", input_tokens=1, output_tokens=1)])
            db.commit()
        url = "/api/admin/ai-overview?days=7"
        assert client.get(url).status_code == 401
        assert client.get(url, headers=actor()).status_code == 403
        admin = actor("admin")
        result = client.get(url, headers=admin)
        assert result.headers["Cache-Control"] == "no-store"
        data = result.json()["data"]
        assert data["summary"] == dict(active_accounts=1, anonymous_sessions=1, conversations=3, turns=3, retries=1, requests=3, failed=1, unreported=1, input_tokens=16, output_tokens=3, reserved_tokens=105)
        assert len(data["trend"]) == 7 and data["trend"][0]["turns"] == 0 and data["trend"][-1]["day"] == "2034-03-04"
        assert data["models"][0]["requests"] == 3
        filtered = client.get(url + "&source=intake", headers=admin).json()["data"]
        assert filtered["summary"]["turns"] == 2 and filtered["summary"]["requests"] == 2
        assert len(filtered["sources"]) == 1


def test_attachments_are_bounded_and_only_passed_to_compatible_models(monkeypatch):
    calls = []
    text_only, vision = SimpleNamespace(supports_vision=False), SimpleNamespace(supports_vision=True)
    monkeypatch.setattr(intake, "resolve_model_targets", lambda *_: [text_only])
    monkeypatch.setattr(dsh, "run_with_fallback", lambda targets, prompt, **kw: calls.append((targets, json.loads(prompt), kw)) or '{"reply":"已分析附件","draft":null}')
    # Minimal SOF fixture for the server's bounded JPEG header check.
    image = {"kind": "image", "name": "screenshot.png", "data": base64.b64encode(bytes.fromhex("ffd8ffc0000b080001000101011100ffd9")).decode()}
    secret_text = "附件原文不应进入状态"
    text = {"kind": "text", "name": "example.log", "data": base64.b64encode(secret_text.encode()).decode()}
    with TestClient(app) as client:
        h = {"X-Intake-Key": uuid4().hex * 2}
        url = "/api/intake/messages"
        assert not client.get("/api/intake/capabilities").json()["data"]["image_input"]
        assert client.post(url, json={"attachments": [image]}, headers=h).status_code == 422
        assert client.post(url, json={"attachments": [{**text, "name": "unknown.zip"}]}, headers=h).status_code == 422
        assert client.post(url, json={"attachments": [{**image, "data": "abcd"}]}, headers=h).status_code == 422
        assert not calls
        monkeypatch.setattr(intake, "resolve_model_targets", lambda *_: [text_only, vision])
        assert client.get("/api/intake/capabilities").json()["data"]["image_input"]
        result = client.post(url, json={"attachments": [image, text]}, headers=h)
        assert result.status_code == 200, result.text
        targets, prompt, options = calls[0]
        assert targets == [vision] and prompt["text_attachments"] == [{"name": "example.log", "content": secret_text}]
        assert options["images"][0]["source"] == {"type": "base64", "media_type": "image/jpeg", "data": image["data"]}
        key = h["X-Intake-Key"]
        state = intake.read_state(result.json()["data"]["state"], intake.principal(None, key), key)
        assert secret_text not in json.dumps(state, ensure_ascii=False) and image["data"] not in str(state)


def test_admin_can_view_new_intake_transcript_but_not_attachment_contents(monkeypatch):
    from requirement_platform.conversation_usage import conversation_usage
    from requirement_platform.models import AuditEvent

    vision = SimpleNamespace(supports_vision=True)
    monkeypatch.setattr(intake, 'resolve_model_targets', lambda *_: [vision])

    def model(targets, prompt, **options):
        assert targets == [vision] and len(options['images']) == 5
        kind, conversation_id, message_id = conversation_usage.get()
        with SessionLocal() as db:
            db.add(ModelRequestUsage(connection_id='vision', connection_name='Vision', model_id='example', model_name='Vision model',
                                     conversation_kind=kind, conversation_id=conversation_id, message_id=message_id,
                                     status='completed', input_tokens=55, output_tokens=7, reserved_tokens=5000))
            db.commit()
        return '{"reply":"关于这组截图的回复","draft":null}'

    monkeypatch.setattr(dsh, 'run_with_fallback', model)
    payload = base64.b64encode(bytes.fromhex('ffd8ffc0000b080001000101011100ffd9')).decode()
    photos = [{'kind':'image', 'name': f'private-file-{i}.png', 'data': payload} for i in range(6)]
    document = {'kind':'text', 'name':'private-log.log', 'data':base64.b64encode(b'private-log-content').decode()}
    with TestClient(app) as client:
        key = uuid4().hex * 2
        h = {'X-Intake-Key': key, 'Accept': 'text/event-stream'}
        intake_url = '/api/intake/messages'
        assert client.post(intake_url, json={'attachments': photos}, headers=h).status_code == 422
        assert client.post(intake_url, json={'attachments': photos[:5] + [document]*4}, headers=h).status_code == 422
        result = client.post(intake_url, json={'content':'行影集的截图出现异常', 'attachments':photos[:5]+[document]}, headers=h)
        assert result.status_code == 200 and 'event: result' in result.text
        cid = intake.intake_id(intake.principal(None, key), key)
        url = f'/api/admin/ai-conversations/{cid}?kind=intake'
        assert client.get(url).status_code == 401
        assert client.get(url, headers=actor()).status_code == 403
        admin = actor('admin')
        data = client.get('/api/admin/ai-conversations?kind=intake', headers=admin).json()['data']
        row = next(x for x in data['items'] if x['id'] == cid)
        assert row['has_transcript'] and row['input_tokens'] == 55
        detail = client.get(url, headers=admin)
        assert detail.status_code == 200 and detail.headers['Cache-Control'] == 'no-store'
        assert all(secret not in detail.text for secret in ('private-file', 'private-log', payload, key))
        msg = detail.json()['data']['items'][0]
        assert (msg['content'], msg['response'], msg['image_count'], msg['file_count']) == ('行影集的截图出现异常','关于这组截图的回复',5,1)
        assert msg['input_tokens'] == 55 and msg['status'] == 'completed'
        with SessionLocal() as db:
            assert db.query(AuditEvent).filter_by(action='conversation.admin_viewed', object_id=cid).count() == 1
