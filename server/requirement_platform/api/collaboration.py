from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .requirements import edit_token_matches
from .responses import ok
from ..collaboration_models import Conversation, ConversationMessage, EmailDelivery, EmailSubscription
from ..conversation_usage import record_chat
from ..db import get_db
from ..domain.common import audit, enqueue
from ..domain.requirements import get_requirement, RequirementNotFound
from ..models import BackgroundJob, User, utcnow
from ..notifications import decode_subscription_token, subscribe
from ..security import manager, optional_user
from ..ai_guard import admit_chat, quota_view, permitted_topic, REFUSAL, consume, digest

router = APIRouter(tags=["collaboration"])


def access(db, requirement_id, user, edit_token):
    try:
        row = get_requirement(db, requirement_id)
    except RequirementNotFound:
        raise HTTPException(404, "需求不存在")
    if user and (row.created_by == user.id or user.role in {"admin", "owner"}):
        return row, f"user:{user.id}"
    if edit_token_matches(row, edit_token):
        return row, f"receipt:{row.id}"
    if edit_token and row.created_by is None:
        try:
            subscription = db.get(EmailSubscription, decode_subscription_token(edit_token, "conversation", db))
            if subscription and subscription.requirement_id == row.id and subscription.verified and subscription.active:
                return row, f"receipt:{row.id}"
        except ValueError:
            pass
    raise HTTPException(403, "仅提交者、持有修改回执者或管理员可以讨论此需求")


def get_conversation(db, requirement, principal):
    return db.query(Conversation).filter_by(requirement_id=requirement.id, principal=principal).first()


def message_data(db, message):
    job = db.query(BackgroundJob).filter_by(job_type="conversation", object_id=message.id).first()
    status = "failed" if job and job.status == "failed" else message.status
    return {"id": message.id, "content": message.content, "response": message.response, "mode": message.mode,
            "status": status, "created_at": message.created_at, "error": "分析暂时失败，请重试" if status == "failed" else None}


class MessageInput(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    client_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    mode: Literal["analysis", "plan", "repair"] = "analysis"


@router.get("/api/requirements/{requirement_id}/conversation")
def read_conversation(requirement_id: str, user: User | None = Depends(optional_user), x_requirement_edit_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    requirement, principal = access(db, requirement_id, user, x_requirement_edit_token)
    conversation = get_conversation(db, requirement, principal)
    messages = db.query(ConversationMessage).filter_by(conversation_id=conversation.id).order_by(ConversationMessage.created_at).all() if conversation else []
    return ok({"messages": [message_data(db, m) for m in messages], "can_plan": bool(user and user.role in {"admin", "owner"}),
               "quota": quota_view(db, principal, principal.startswith("receipt:"), len(messages))})


@router.post("/api/requirements/{requirement_id}/conversation")
def send_message(requirement_id: str, payload: MessageInput, request: Request, user: User | None = Depends(optional_user), x_requirement_edit_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    requirement, principal = access(db, requirement_id, user, x_requirement_edit_token)
    if payload.mode != "analysis" and not (user and user.role in {"admin", "owner"}):
        raise HTTPException(403, "方案和修复模式需要管理员权限")
    conversation = get_conversation(db, requirement, principal)
    if not conversation:
        conversation = Conversation(requirement_id=requirement.id, principal=principal)
        db.add(conversation)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            conversation = get_conversation(db, requirement, principal)
    existing = db.query(ConversationMessage).filter_by(conversation_id=conversation.id, client_id=payload.client_id).first()
    if existing:
        if existing.content != payload.content or existing.mode != payload.mode:
            raise HTTPException(409, "消息回执已使用")
        return ok(message_data(db, existing))
    if not payload.content.strip():
        raise HTTPException(422, "请填写讨论内容")
    # Serialize admission in SQLite before inspecting pending work.
    db.query(Conversation).filter_by(id=conversation.id).update({"principal": Conversation.principal}, synchronize_session=False)
    pending = db.query(ConversationMessage).filter_by(conversation_id=conversation.id).filter(ConversationMessage.status.in_(["queued", "running"])).all()
    if any(message_data(db, m)["status"] != "failed" for m in pending):
        raise HTTPException(409, "请等待上一条消息完成")
    count = db.query(ConversationMessage).filter_by(conversation_id=conversation.id).count()
    if count >= 100:
        raise HTTPException(429, "此对话已达到 100 条消息上限")
    admit_chat(db, principal, request.client.host if request.client else "unknown", principal.startswith("receipt:"))
    record_chat(db, "requirement", conversation.id, principal)
    message = ConversationMessage(conversation_id=conversation.id, **payload.model_dump())
    allowed = permitted_topic(payload.content, requirement.title + " " + requirement.description)
    if not allowed:
        message.status, message.response = "completed", REFUSAL
    db.add(message)
    db.flush()
    if allowed:
        enqueue(db, "conversation", message.id, f"conversation:{message.id}")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "消息已提交，请刷新对话")
    return ok(message_data(db, message))


@router.post("/api/requirements/{requirement_id}/conversation/{message_id}/retry")
def retry_message(requirement_id: str, message_id: str, request: Request, user: User | None = Depends(optional_user), x_requirement_edit_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    requirement, principal = access(db, requirement_id, user, x_requirement_edit_token)
    conversation = get_conversation(db, requirement, principal)
    message = db.get(ConversationMessage, message_id)
    if not conversation or not message or message.conversation_id != conversation.id:
        raise HTTPException(404, "消息不存在")
    job = db.query(BackgroundJob).filter_by(job_type="conversation", object_id=message.id, status="failed").first()
    if not job:
        raise HTTPException(409, "此消息无需重试")
    db.query(Conversation).filter_by(id=conversation.id).update({"principal": Conversation.principal}, synchronize_session=False)
    others = db.query(ConversationMessage).filter(ConversationMessage.conversation_id == conversation.id, ConversationMessage.id != message.id, ConversationMessage.status.in_(["queued", "running"])).all()
    if any(message_data(db, m)["status"] != "failed" for m in others):
        raise HTTPException(409, "请等待上一条消息完成")
    admit_chat(db, principal, request.client.host if request.client else "unknown", principal.startswith("receipt:"))
    record_chat(db, "requirement", conversation.id, principal, retry=True)
    job.status, job.attempts, job.available_at, job.last_error = "queued", 0, utcnow(), None
    message.status = "queued"
    db.commit()
    return ok(message_data(db, message))


class SubscriptionInput(BaseModel):
    email: EmailStr


@router.post("/api/requirements/{requirement_id}/notifications")
def subscribe_requirement(requirement_id: str, payload: SubscriptionInput, request: Request, user: User | None = Depends(optional_user), x_requirement_edit_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    requirement, _ = access(db, requirement_id, user, x_requirement_edit_token)
    consume(db, f"email-ip:{digest(request.client.host if request.client else 'unknown')}", 10, 3600)
    subscribe(db, requirement, payload.email)
    db.commit()
    return ok(None, "请检查邮箱并确认订阅")


class TokenInput(BaseModel):
    token: str = Field(max_length=4096)


@router.post("/api/notifications/{action}")
def confirm_subscription(action: Literal["verify", "unsubscribe"], payload: TokenInput, db: Session = Depends(get_db)):
    try:
        subscription_id = decode_subscription_token(payload.token, action, db)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    row = db.get(EmailSubscription, subscription_id)
    if not row:
        raise HTTPException(404, "订阅不存在")
    if action == "verify":
        if not row.active:
            raise HTTPException(409, "订阅已取消，请重新申请")
        row.verified = True
    else:
        row.active = False
        from ..models import new_id
        row.token_version = new_id()
    db.commit()
    return ok(None, "邮箱已确认" if action == "verify" else "已退订")


class ConsultationInput(BaseModel):
    body: str = Field(min_length=4, max_length=4000)


@router.post("/api/requirements/{requirement_id}/consultations")
def consult(requirement_id: str, payload: ConsultationInput, actor: User = Depends(manager), db: Session = Depends(get_db)):
    requirement, _ = access(db, requirement_id, actor, None)
    # Store the question in the submitter's conversation, never in public metadata.
    principal = f"user:{requirement.created_by}" if requirement.created_by else f"receipt:{requirement.id}"
    conversation = get_conversation(db, requirement, principal)
    if not conversation:
        conversation = Conversation(requirement_id=requirement.id, principal=principal)
        db.add(conversation)
        db.flush()
    from ..models import new_id
    message = ConversationMessage(conversation_id=conversation.id, client_id=new_id(), mode="consultation", content="维护者咨询", response=payload.body, status="completed")
    db.add(message)
    audit(db, actor.id, "consultation.created", "requirement", requirement.id)
    db.commit()
    return ok(None, "咨询已保存并排队通知")


@router.get("/api/admin/notifications")
def list_notifications(actor: User = Depends(manager), db: Session = Depends(get_db)):
    rows = db.query(EmailDelivery).order_by(EmailDelivery.created_at.desc()).limit(100).all()
    return ok([{ "id": r.id, "kind": r.kind, "status": r.status, "attempts": r.attempts, "last_error": r.last_error, "created_at": r.created_at} for r in rows])


@router.post("/api/admin/notifications/{delivery_id}/retry")
def retry_notification(delivery_id: str, actor: User = Depends(manager), db: Session = Depends(get_db)):
    row = db.get(EmailDelivery, delivery_id)
    if not row or row.status != "failed":
        raise HTTPException(409, "只能重试失败的通知")
    row.status, row.attempts, row.available_at, row.last_error = "queued", 0, utcnow(), None
    db.commit()
    return ok(None)
