"""Provider-reported usage, stored without prompts, responses, principals or keys."""
import json
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from .api.responses import ok
from .collaboration_models import ModelRequestUsage
from .db import get_db
from .models import AIConnection, AIModel, User, utcnow
from .security import manager

router = APIRouter(prefix="/api/admin/ai-model-usage", tags=["model-usage"])


def reported_usage(body):
    """Handle JSON and Messages SSE; counters in streaming events are cumulative."""
    values = []
    try:
        values.append(json.loads(body))
    except (ValueError, UnicodeDecodeError):
        for line in body.splitlines():
            if line.startswith(b"data:"):
                try:
                    values.append(json.loads(line[5:].strip()))
                except (ValueError, UnicodeDecodeError):
                    pass
    input_tokens = output_tokens = None
    for event in values:
        if not isinstance(event, dict):
            continue
        message = event.get("message")
        usage = event.get("usage") or (message.get("usage") if isinstance(message, dict) else None)
        if not isinstance(usage, dict):
            continue
        def count(name):
            value = usage.get(name)
            return value if type(value) is int and 0 <= value <= 1000000000 else None
        incoming = count("input_tokens")
        if incoming is not None:
            incoming += (count("cache_read_input_tokens") or 0) + (count("cache_creation_input_tokens") or 0)
            input_tokens = max(input_tokens or 0, incoming)
        outgoing = count("output_tokens")
        if outgoing is not None:
            output_tokens = max(output_tokens or 0, outgoing)
    return input_tokens, output_tokens


@router.get("")
def usage(days: int = Query(default=30, ge=1, le=90), actor: User = Depends(manager), db: Session = Depends(get_db)):
    today = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = db.query(
        ModelRequestUsage.connection_id, func.max(ModelRequestUsage.connection_name).label("connection_name"),
        ModelRequestUsage.model_id, func.max(ModelRequestUsage.model_name).label("model_name"),
        func.count().label("requests"),
        func.sum(case((ModelRequestUsage.status == "failed", 1), else_=0)).label("failed"),
        func.sum(case((ModelRequestUsage.input_tokens.is_(None) | ModelRequestUsage.output_tokens.is_(None), 1), else_=0)).label("unreported"),
        func.coalesce(func.sum(ModelRequestUsage.input_tokens), 0).label("input_tokens"),
        func.coalesce(func.sum(ModelRequestUsage.output_tokens), 0).label("output_tokens"),
        func.coalesce(func.sum(ModelRequestUsage.reserved_tokens), 0).label("reserved_tokens"),
        func.coalesce(func.sum(case((ModelRequestUsage.created_at >= today, func.coalesce(ModelRequestUsage.input_tokens, 0) + func.coalesce(ModelRequestUsage.output_tokens, 0)), else_=0)), 0).label("today_tokens"),
    ).filter(ModelRequestUsage.created_at >= today - timedelta(days=days - 1)).group_by(
        ModelRequestUsage.connection_id, ModelRequestUsage.model_id,
    ).all()
    data = {(r.connection_id, r.model_id): dict(r._mapping) for r in rows}
    for model, connection in db.query(AIModel, AIConnection).join(AIConnection, AIModel.connection_id == AIConnection.id):
        row = data.setdefault((connection.id, model.id), dict(connection_id=connection.id, model_id=model.id, requests=0, failed=0, unreported=0, input_tokens=0, output_tokens=0, reserved_tokens=0, today_tokens=0))
        row.update(connection_name=connection.name, model_name=model.model_name)
    return ok({"days": days, "models": list(data.values())})
