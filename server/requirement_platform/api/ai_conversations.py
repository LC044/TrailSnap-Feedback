"""Manager-only conversation usage and recorded transcripts."""
from datetime import timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import case, func, literal
from sqlalchemy.orm import Session

from .responses import ok
from ..collaboration_models import Conversation, ConversationMessage, IntakeConversationMessage, ModelRequestUsage as Usage
from ..db import get_db
from ..domain.common import audit
from ..models import Requirement, User
from ..security import manager

router = APIRouter(prefix="/api/admin/ai-conversations", tags=["ai-conversations"], dependencies=[Depends(manager)])


def usage_columns():
    return (
        func.count(Usage.id).label("requests"),
        func.sum(case((Usage.status == "failed", 1), else_=0)).label("failed"),
        func.sum(case((Usage.input_tokens.is_(None) | Usage.output_tokens.is_(None), 1), else_=0)).label("unreported"),
        func.sum(Usage.input_tokens).label("input_tokens"),
        func.sum(Usage.output_tokens).label("output_tokens"),
        func.sum(Usage.reserved_tokens).label("reserved_tokens"),
    )


def counts(row):
    return {key: (getattr(row, key, None) or 0) for key in
            ("requests", "failed", "unreported", "input_tokens", "output_tokens", "reserved_tokens")}


def timestamp(value):
    return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value).isoformat()


@router.get("")
def list_conversations(response: Response, kind: Literal["requirement", "intake"] = "requirement",
                       page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=50), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    if kind == "intake":
        turns = db.query(IntakeConversationMessage.conversation_id.label("id"),
                         func.max(IntakeConversationMessage.created_at).label("updated_at"),
                         literal(1).label("has_transcript")).group_by(IntakeConversationMessage.conversation_id)
        legacy = db.query(Usage.conversation_id.label("id"), func.max(Usage.created_at).label("updated_at"),
                          literal(0).label("has_transcript")).filter(
            Usage.conversation_kind == kind, Usage.conversation_id.is_not(None),
        ).group_by(Usage.conversation_id)
        combined = turns.union_all(legacy).subquery()
        latest = func.max(combined.c.updated_at)
        query = db.query(combined.c.id, latest.label("updated_at"),
                         func.max(combined.c.has_transcript).label("has_transcript")).group_by(combined.c.id)
        count = query.count()
        rows = query.order_by(latest.desc(), combined.c.id.desc()).offset((page - 1) * limit).limit(limit).all()
    else:
        latest = func.max(ConversationMessage.created_at)
        query = db.query(Conversation.id, Requirement.public_number, Requirement.title, latest.label("updated_at")).join(
            Requirement, Requirement.id == Conversation.requirement_id,
        ).join(ConversationMessage, ConversationMessage.conversation_id == Conversation.id).filter(
            Requirement.deleted_at.is_(None),
        ).group_by(Conversation.id, Requirement.public_number, Requirement.title)
        count = query.count()
        rows = query.order_by(latest.desc(), Conversation.id.desc()).offset((page - 1) * limit).limit(limit).all()
    totals = {row.conversation_id: counts(row) for row in db.query(Usage.conversation_id, *usage_columns()).filter(
        Usage.conversation_kind == kind, Usage.conversation_id.in_([row.id for row in rows]),
    ).group_by(Usage.conversation_id)} if rows else {}
    return ok({"total": count, "items": [{
        "id": row.id, "updated_at": timestamp(row.updated_at), "has_transcript": bool(getattr(row, "has_transcript", True)),
        "requirement_number": getattr(row, "public_number", None), "title": getattr(row, "title", None),
        **(totals.get(row.id) or counts(None)),
    } for row in rows]})


@router.get("/{conversation_id}")
def conversation_detail(conversation_id: UUID, response: Response, kind: Literal["requirement", "intake"] = "requirement",
                        page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=50),
                        actor: User = Depends(manager), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    cid = str(conversation_id)
    model = IntakeConversationMessage if kind == "intake" else ConversationMessage
    query = db.query(model).filter_by(conversation_id=cid)
    if kind == "requirement" and not db.query(Conversation.id).join(Requirement, Requirement.id == Conversation.requirement_id).filter(
        Conversation.id == cid, Requirement.deleted_at.is_(None),
    ).first():
        raise HTTPException(404, "Conversation not found")
    total = query.count()
    if kind == "intake" and not total:
        raise HTTPException(404, "此会话没有可查看的对话正文")
    rows = query.order_by(model.created_at.desc(), model.id.desc()).offset((page - 1) * limit).limit(limit).all()
    totals = {row.message_id: counts(row) for row in db.query(Usage.message_id, *usage_columns()).filter(
        Usage.conversation_kind == kind, Usage.conversation_id == cid, Usage.message_id.in_([row.id for row in rows]),
    ).group_by(Usage.message_id)} if rows else {}
    traces = {}
    if rows:
        recorded = db.query(Usage.message_id, Usage.tool_calls).filter(
            Usage.conversation_kind == kind, Usage.conversation_id == cid,
            Usage.message_id.in_([row.id for row in rows]), Usage.tool_calls.is_not(None),
        ).all()
        for message_id, calls in recorded:
            if calls is not None:
                traces.setdefault(message_id, []).extend(calls)
        for calls in traces.values():
            calls.sort(key=lambda call: call["created_at"])
    audit(db, actor.id, "conversation.admin_viewed", "conversation", cid, page=page, kind=kind)
    db.commit()
    return ok({"total": total, "items": [{
        "id": row.id, "created_at": timestamp(row.created_at), "mode": row.mode, "status": row.status,
        "content": row.content, "response": row.response, **(totals.get(row.id) or counts(None)),
        "tool_calls": traces.get(row.id),
        "image_count": getattr(row, "image_count", 0), "file_count": getattr(row, "file_count", 0),
    } for row in rows]})
