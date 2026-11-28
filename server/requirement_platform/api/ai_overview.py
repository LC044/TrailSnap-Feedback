"""Read-only AI activity dashboard; no actor identifiers in the response."""
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Response
from sqlalchemy import case, distinct, func
from sqlalchemy.orm import Session

from .ai_conversations import counts, usage_columns
from .responses import ok
from ..collaboration_models import AIChatActivity as Chat, ModelRequestUsage as Usage
from ..db import get_db
from ..models import utcnow
from ..security import manager

router = APIRouter(prefix="/api/admin/ai-overview", tags=["ai-overview"], dependencies=[Depends(manager)])


def activity_columns():
    return (
        func.count(distinct(case((Chat.anonymous.is_(False), Chat.actor_key)))).label("active_accounts"),
        func.count(distinct(case((Chat.anonymous.is_(True), Chat.actor_key)))).label("anonymous_sessions"),
        func.count(distinct(Chat.conversation_id)).label("conversations"),
        func.count(case((Chat.retry.is_(False), 1))).label("turns"),
        func.count(case((Chat.retry.is_(True), 1))).label("retries"),
    )


def activity(row):
    return {name: getattr(row, name, 0) or 0 for name in
            ("active_accounts", "anonymous_sessions", "conversations", "turns", "retries")}


@router.get("")
def overview(response: Response, days: Literal["7", "30", "90"] = "30",
             source: Literal["all", "requirement", "intake", "background"] = "all", db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    end = utcnow().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    start = end - timedelta(days=int(days))
    chat_filter = [Chat.created_at >= start, Chat.created_at < end]
    usage_filter = [Usage.created_at >= start, Usage.created_at < end]
    if source in {"requirement", "intake"}:
        chat_filter.append(Chat.kind == source)
        usage_filter.append(Usage.conversation_kind == source)
    elif source == "background":
        chat_filter.append(Chat.kind == source)  # No chat activity for unassociated calls.
        usage_filter.append(Usage.conversation_kind.is_(None))

    chat_day = func.date(Chat.created_at)
    model_day = func.date(Usage.created_at)
    chat_daily = {r.day: activity(r) for r in db.query(chat_day.label("day"), *activity_columns()).filter(*chat_filter).group_by(chat_day)}
    model_daily = {r.day: counts(r) for r in db.query(model_day.label("day"), *usage_columns()).filter(*usage_filter).group_by(model_day)}
    trend = []
    for offset in range(int(days)):
        key = (start + timedelta(days=offset)).date().isoformat()
        trend.append({"day": key, **chat_daily.get(key, activity(None)), **model_daily.get(key, counts(None))})

    usage_source = func.coalesce(Usage.conversation_kind, "background")
    source_activity = {r.kind: activity(r) for r in db.query(Chat.kind, *activity_columns()).filter(*chat_filter).group_by(Chat.kind)}
    source_usage = {r.kind: counts(r) for r in db.query(usage_source.label("kind"), *usage_columns()).filter(*usage_filter).group_by(usage_source)}
    sources = [{"kind": kind, **source_activity.get(kind, activity(None)), **source_usage.get(kind, counts(None))}
               for kind in ("intake", "requirement", "background") if source == "all" or source == kind]

    models = db.query(Usage.connection_id, Usage.model_id, func.max(Usage.connection_name).label("connection_name"),
                      func.max(Usage.model_name).label("model_name"), *usage_columns()).filter(*usage_filter).group_by(
        Usage.connection_id, Usage.model_id,
    ).order_by(func.count(Usage.id).desc(), Usage.connection_id, Usage.model_id).limit(50)
    tracking_since = db.query(func.min(Chat.created_at)).scalar()
    return ok({
        "tracking_since": tracking_since.date().isoformat() if tracking_since else None,
        "summary": {**activity(db.query(*activity_columns()).filter(*chat_filter).one()),
                    **counts(db.query(*usage_columns()).filter(*usage_filter).one())},
        "trend": trend, "sources": sources,
        "models": [{"id": f"{r.connection_id}:{r.model_id}", "connection_name": r.connection_name, "model_name": r.model_name, **counts(r)} for r in models],
    })
