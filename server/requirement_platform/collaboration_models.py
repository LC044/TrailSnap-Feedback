"""Durable conversations and transactional email outbox."""
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .models import new_id, utcnow


class AIQuota(Base):
    __tablename__ = "ai_quotas"
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    used: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[object] = mapped_column(DateTime(timezone=True), index=True)


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
