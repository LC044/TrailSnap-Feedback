import json
import re

from .ai_settings import resolve_model_targets
from .collaboration_models import Conversation, ConversationMessage
from .conversation_usage import track_conversation
from .domain.common import audit
from .models import Requirement, User
from . import dsh
from .ai_guard import permitted_topic, REFUSAL, chat_budget


def process_message(db, message_id):
    message = db.get(ConversationMessage, message_id)
    if not message or message.status == "completed":
        return
    conversation = db.get(Conversation, message.conversation_id)
    requirement = db.get(Requirement, conversation.requirement_id)
    if not requirement or requirement.deleted_at:
        raise RuntimeError("需求已不可用")
    # Recheck privileges when the queued work actually runs.
    user = db.get(User, conversation.principal.removeprefix("user:")) if conversation.principal.startswith("user:") else None
    manager = bool(user and user.is_active and user.role in {"admin", "owner"})
    if conversation.principal.startswith("user:") and (not user or not user.is_active or (requirement.created_by != user.id and not manager)):
        raise RuntimeError("对话权限已失效")
    if message.mode != "analysis" and not manager:
        raise RuntimeError("管理员权限已失效")
    if not permitted_topic(message.content, requirement.title + " " + requirement.description):
        message.response, message.status = REFUSAL, "completed"
        db.commit()
        return
    targets = resolve_model_targets(db, "requirement_triage" if message.mode == "analysis" else "spec_drafting" if message.mode == "plan" else "coding")
    if not targets:
        raise RuntimeError("管理员尚未配置此任务的 AI 模型")
    history = db.query(ConversationMessage).filter_by(conversation_id=conversation.id, status="completed").order_by(ConversationMessage.created_at.desc()).limit(4).all()
    context = {"task": message.mode, "requirement": {"title": requirement.title, "description": requirement.description, "expected_behavior": requirement.expected_behavior, "steps_to_reproduce": requirement.steps_to_reproduce},
               "history": [{"user": r.content[:500], "assistant": (r.response or '')[:800]} for r in reversed(history)], "user_message": message.content}
    message.status = "running"
    db.commit()
    try:
        with (
            chat_budget(conversation.principal, not conversation.principal.startswith("user:")),
            track_conversation("requirement", conversation.id, message.id),
        ):
            response = dsh.run_with_fallback(targets, json.dumps(context, ensure_ascii=False), session_id=message.id)
    except Exception:
        raise RuntimeError("AI 暂时不可用，请稍后重试或联系管理员")
    response = re.sub(r"deepseek(?:[-\s]+harness)?|\bdsh\b", "行影集 AI 助手", response, flags=re.I)
    message.response, message.status = response, "completed"
    # AI outputs do not alter approved requirements or execution authorizations.
    audit(db, user.id if user else None, "conversation.responded", "conversation", conversation.id, message_id=message.id)
    db.commit()
