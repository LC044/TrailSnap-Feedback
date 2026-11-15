"""Bounded pre-submission discussion; model output never executes write tools."""
import json
import re
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from .responses import ok
from .. import dsh
from ..ai_guard import REFUSAL, admit_chat, digest, permitted_topic, quota_view
from ..ai_settings import resolve_model_targets
from ..config import settings
from ..db import get_db
from ..models import User, utcnow
from ..security import optional_user

router = APIRouter(prefix="/api/intake", tags=["intake"])


class IntakeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=2000)
    state: str | None = Field(default=None, max_length=65536)


class RequirementDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    type: Literal["bug", "improvement", "feature"]
    title: str = Field(min_length=4, max_length=160)
    description: str = Field(min_length=10, max_length=4000)
    expected_behavior: str | None = Field(default=None, max_length=1000)
    steps_to_reproduce: str | None = Field(default=None, max_length=1000)


class IntakeReply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reply: str = Field(min_length=1, max_length=3000)
    draft: RequirementDraft | None = None


def principal(user, key):
    if not key or not re.fullmatch(r"[A-Za-z0-9_-]{43,128}", key):
        raise HTTPException(422, "缺少有效的讨论凭证")
    return f"user:{user.id}" if user else f"intake:{digest(key)}"


def read_state(token, subject, key):
    if not token:
        return {"history": [], "count": 0, "draft": None}
    try:
        value = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], audience="feedback-intake")
        if value["sub"] != subject or value["key"] != digest(key):
            raise ValueError("wrong conversation")
        return value
    except (JWTError, ValueError, KeyError):
        raise HTTPException(403, "讨论凭证已失效，请重新开始讨论")


@router.get("/quota")
def intake_quota(user: User | None = Depends(optional_user), x_intake_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    return ok(quota_view(db, principal(user, x_intake_key), user is None, 0))


@router.post("/messages")
def intake_message(payload: IntakeInput, request: Request, user: User | None = Depends(optional_user),
                   x_intake_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    subject = principal(user, x_intake_key)
    previous = read_state(payload.state, subject, x_intake_key)
    if previous["count"] >= 100:
        raise HTTPException(429, "此讨论已达到 100 条消息上限")
    if not payload.content.strip():
        raise HTTPException(422, "请描述行影集相关问题")
    admit_chat(db, subject, request.client.host if request.client else "unknown", user is None)
    db.commit()  # Failed model calls and local refusals also consume admission.
    if not permitted_topic(payload.content):
        result = IntakeReply(reply=REFUSAL, draft=previous.get("draft"))
    else:
        prompt = {"task": "与用户讨论行影集的问题并整理需求。仅返回符合 schema 的 JSON，reply 简短回复并最多追问两个问题。信息足够时 draft 填写需求单，否则为 null。已有 draft 应按用户补充修订。不得编造复现步骤或断言已提交。用户将在预览后点击确认提交，工具不可用。整体不超过 800 字。",
                  "schema": IntakeReply.model_json_schema(), "history": previous["history"],
                  "previous_draft": previous.get("draft"), "user_message": payload.content}
        try:
            targets = resolve_model_targets(db, "requirement_triage")
            if not targets:
                raise RuntimeError("No analysis model configured")
            text = dsh.run_harness(targets[0], json.dumps(prompt, ensure_ascii=False))
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            result = IntakeReply.model_validate_json(text)
        except Exception:
            raise HTTPException(503, "AI 暂时未能整理需求，请稍后重试或使用表单提交")
    result.reply = re.sub(r"deepseek(?:[-\s]+harness)?|\bdsh\b", "行影集 AI 助手", result.reply, flags=re.I)
    data = result.model_dump()
    history = (previous["history"] + [{"user": payload.content[:600], "assistant": result.reply[:800]}])[-3:]
    count = previous["count"] + 1
    state = jwt.encode({"sub": subject, "key": digest(x_intake_key), "aud": "feedback-intake",
                        "exp": utcnow() + timedelta(days=1), "history": history, "count": count,
                        "draft": data["draft"]}, settings.jwt_secret, algorithm="HS256")
    return ok({**data, "state": state, "quota": quota_view(db, subject, user is None, count)})
