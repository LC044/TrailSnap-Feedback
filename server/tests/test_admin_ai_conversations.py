from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func

from requirement_platform.collaboration_models import Conversation, ConversationMessage, ModelRequestUsage
from requirement_platform.db import SessionLocal
from requirement_platform.main import app
from requirement_platform.models import AuditEvent, Requirement
from test_z_collaboration import actor


@pytest.fixture
def requirement_factory():
    ids = []

    def create(**kwargs):
        with SessionLocal() as db:
            number = (db.query(func.max(Requirement.public_number)).scalar() or 0) + 1
            row = Requirement(public_number=number, type="feature", description="Test requirement", **kwargs)
            db.add(row)
            db.commit()
            ids.append(row.id)
            return row.id

    yield create
    with SessionLocal() as db:
        db.query(Requirement).filter(Requirement.id.in_(ids)).delete(synchronize_session=False)
        db.commit()


def test_ai_conversation_usage_and_transcript_are_manager_only(requirement_factory):
    with TestClient(app) as client:
        admin = actor("admin")
        viewer = actor()
        rid = requirement_factory(title="Test conversation")
        with SessionLocal() as db:
            conversation = Conversation(requirement_id=rid, principal="private-principal")
            db.add(conversation)
            db.flush()
            cid = conversation.id
            turn = ConversationMessage(conversation_id=cid, client_id="turn", content="private-prompt", response="private-answer")
            db.add(turn)
            db.flush()
            iid = str(uuid4())
            provider = dict(connection_id="provider", connection_name="API", model_id="model", model_name="AI", reserved_tokens=1200)
            trace = {"name": "grep", "created_at": "2026-01-01T00:00:00+00:00", "status": "completed"}
            db.add_all([
                ModelRequestUsage(**provider, input_tokens=999, output_tokens=999),  # before linkage
                ModelRequestUsage(**provider, conversation_kind="requirement", conversation_id=cid, message_id=turn.id,
                                  input_tokens=100, output_tokens=20, status="completed", tool_calls=[trace]),
                ModelRequestUsage(**provider, conversation_kind="requirement", conversation_id=cid, message_id=turn.id, status="failed"),
                ModelRequestUsage(**provider, conversation_kind="intake", conversation_id=iid, input_tokens=7, output_tokens=2, status="completed"),
            ])
            db.commit()
        path = "/api/admin/ai-conversations"
        for url in (path, f"{path}/{cid}", f"{path}?kind=intake"):
            assert client.get(url).status_code == 401
            assert client.get(url, headers=viewer).status_code == 403
        result = client.get(path, headers=admin)
        assert result.headers["Cache-Control"] == "no-store"
        assert "private-prompt" not in result.text and "private-principal" not in result.text
        row = next(row for row in result.json()["data"]["items"] if row["id"] == cid)
        assert (row["requests"], row["failed"], row["unreported"]) == (2, 1, 1)
        assert (row["input_tokens"], row["output_tokens"], row["reserved_tokens"]) == (100, 20, 2400)
        result = client.get(f"{path}/{cid}", headers=admin)
        assert result.headers["Cache-Control"] == "no-store"
        turn = result.json()["data"]["items"][0]
        assert (turn["content"], turn["response"], turn["input_tokens"]) == ("private-prompt", "private-answer", 100)
        assert turn["tool_calls"] == [trace]
        assert "tool_calls" not in row
        result = client.get(f"{path}?kind=intake", headers=admin)
        intake = next(row for row in result.json()["data"]["items"] if row["id"] == iid)
        assert intake["input_tokens"] == 7 and intake["requirement_number"] is None
        assert client.get(f"{path}/{iid}", headers=admin).status_code == 404
        with SessionLocal() as db:
            assert db.query(AuditEvent).filter_by(action="conversation.admin_viewed", object_id=cid).count() == 1


def test_public_completed_stage_filters_closed_and_released_without_leaking_private_requirements(requirement_factory):
    key = uuid4().hex
    with TestClient(app) as client:
        admin = actor("admin")
        statuses = ["closed", "released", "release_ready", "closed"]
        rows = [requirement_factory(title=f"行影集 {key}-{i}", status=status, visibility="private" if i == 3 else "public")
                for i, status in enumerate(statuses)]
        for headers in ({}, admin):
            result = client.get(f"/api/requirements?stage=done&public_only=true&q={key}", headers=headers)
            assert result.status_code == 200
            assert {row["id"] for row in result.json()["data"]} == {rows[0], rows[1]}
        result = client.get(f"/api/requirements?status=closed,released&q={key}")
        assert {row["status"] for row in result.json()["data"]} == {"closed", "released"}
        result = client.get(f"/api/requirements?public_only=true&q={key}", headers=admin)
        assert {row["id"] for row in result.json()["data"]} == {rows[1], rows[2]}
