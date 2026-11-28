"""Durable conversations and transactional email outbox."""
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .models import new_id, utcnow


class AIQuota(Base):
    __tablename__ = "ai_quotas"
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    used: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[object] = mapped_column(DateTime(timezone=True), index=True)


class AIQuotaPolicy(Base):
    __tablename__ = "ai_quota_policy"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)


class MailSettings(Base):
    __tablename__ = "mail_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    accounts: Mapped[list] = mapped_column(JSON, default=list)
    cursor: Mapped[int] = mapped_column(Integer, default=0)


class ModelRequestUsage(Base):
    __tablename__ = "model_request_usage"
    __table_args__ = (Index("ix_model_usage_conversation", "conversation_kind", "conversation_id", "message_id"),)
    conversation_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    connection_id: Mapped[str] = mapped_column(String(36), index=True)
    connection_name: Mapped[str] = mapped_column(String(160))
    model_id: Mapped[str] = mapped_column(String(36), index=True)
    model_name: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    reserved_tokens: Mapped[int] = mapped_column(Integer)
    tool_calls: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class AIChatActivity(Base):
    __tablename__ = "ai_chat_activity"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(16))
    conversation_id: Mapped[str] = mapped_column(String(36))
    actor_key: Mapped[str] = mapped_column(String(64))
    anonymous: Mapped[bool] = mapped_column(Boolean)
    retry: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class KnowledgeSnapshot(Base):
    __tablename__ = "knowledge_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tag: Mapped[str] = mapped_column(String(100))
    revision: Mapped[str] = mapped_column(String(40))
    index_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    refreshed_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)
    docs_count: Mapped[int] = mapped_column(Integer, default=0)
    code_count: Mapped[int] = mapped_column(Integer, default=0)
    warning: Mapped[str | None] = mapped_column(String(255), nullable=True)


class KnowledgeFile(Base):
    __tablename__ = "knowledge_files"
    path: Mapped[str] = mapped_column(String(500), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)
    url: Mapped[str] = mapped_column(String(1000))
    content: Mapped[str] = mapped_column(Text)


class EmailSubscription(Base):
    __tablename__ = "email_subscriptions"
    __table_args__ = (UniqueConstraint("requirement_id", "email"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    requirement_id: Mapped[str] = mapped_column(ForeignKey("requirements.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(255))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    token_version: Mapped[str] = mapped_column(String(36), default=new_id)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class EmailDelivery(Base):
    __tablename__ = "email_deliveries"
    __table_args__ = (Index("ix_email_due", "status", "available_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    subscription_id: Mapped[str] = mapped_column(ForeignKey("email_subscriptions.id", ondelete="CASCADE"), index=True)
    event_key: Mapped[str] = mapped_column(String(200), unique=True)
    kind: Mapped[str] = mapped_column(String(40))
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)
    lease_expires_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (UniqueConstraint("requirement_id", "principal"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    requirement_id: Mapped[str] = mapped_column(ForeignKey("requirements.id", ondelete="CASCADE"), index=True)
    principal: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (UniqueConstraint("conversation_id", "client_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[str] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(24), default="analysis")
    content: Mapped[str] = mapped_column(Text)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class IntakeConversationMessage(Base):
    __tablename__ = "intake_conversation_messages"
    __table_args__ = (Index("ix_intake_message_conversation_time", "conversation_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(String(36))
    mode: Mapped[str] = mapped_column(String(24))
    content: Mapped[str] = mapped_column(Text)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")
    image_count: Mapped[int] = mapped_column(Integer, default=0)
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)
