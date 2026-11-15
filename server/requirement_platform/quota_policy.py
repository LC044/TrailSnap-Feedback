"""Persistent administrator policy; counters are never reset by configuration edits."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .collaboration_models import AIQuotaPolicy
from .config import settings


class QuotaPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["count", "tokens", "both"] = "count"
    anonymous_daily: int = Field(default=10, ge=0, le=100000)
    user_daily: int = Field(default=30, ge=0, le=100000)
    anonymous_tokens: int = Field(default=100000, ge=0, le=100000000)
    user_tokens: int = Field(default=300000, ge=0, le=100000000)
    ip_daily: int = Field(default=60, ge=0, le=1000000)
    global_daily: int = Field(default=200, ge=0, le=1000000)
    global_tokens: int = Field(default=1000000, ge=0, le=1000000000)
    interval_seconds: int = Field(default=20, ge=1, le=3600)


def read_policy(db):
    row = db.get(AIQuotaPolicy, 1)
    if row:
        return QuotaPolicy.model_validate(row.config)
    return QuotaPolicy(anonymous_daily=settings.ai_anonymous_daily, user_daily=settings.ai_user_daily,
                       ip_daily=settings.ai_ip_daily, global_daily=settings.ai_global_daily,
                       global_tokens=settings.ai_daily_token_budget, interval_seconds=settings.ai_interval_seconds)
