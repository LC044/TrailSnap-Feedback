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
from ..ai_guard import REFUSAL, admit_chat, chat_budget, digest, permitted_topic, quota_view
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
    mode: Literal["feedback", "bug", "consultation"] | None = None


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


@router.get("/knowledge")
def knowledge_status(db: Session = Depends(get_db)):
    from ..knowledge import status
    return ok(status(db))


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
    context = json.dumps(previous.get("draft"), ensure_ascii=False) if previous.get("draft") else " ".join(
        turn["user"] for turn in previous["history"] if turn.get("assistant") != REFUSAL)
    if previous.get("topic_established"):
        context += " 行影集"
    allowed = permitted_topic(payload.content, context)
    knowledge = None
    if not allowed:
        result = IntakeReply(reply=REFUSAL, draft=previous.get("draft"))
    else:
        prompt = {"task": "与用户讨论行影集的问题并整理需求。仅返回符合 schema 的 JSON，reply 简短回复并最多追问两个问题。信息足够时 draft 填写需求单，否则为 null。已有 draft 应按用户补充修订。不得编造复现步骤或断言已提交。用户将在预览后点击确认提交，工具不可用。整体不超过 800 字。",
                  "schema": IntakeReply.model_json_schema(), "history": previous["history"],
                  "previous_draft": previous.get("draft"), "user_message": payload.content}
        try:
            if payload.mode:
                from ..knowledge import ReadOnlyKnowledge
                knowledge = ReadOnlyKnowledge()
                prompt["mode"] = payload.mode
                prompt["snapshot"] = knowledge.snapshot
                prompt["task"] = (
                    "回答行影集相关问题，仅返回 schema JSON。feedback 模式讨论需求并整理草稿，bug 模式结合代码分析原因、给出修复建议并整理 bug 草稿；"
                    "consultation 模式解答使用问题，draft 必须为 null。先用只读工具检索：使用咨询优先检索官网文档，bug 或新需求优先检索源码，必要时再读具体片段。"
                    "最多六次工具查询、最多三轮模型请求，尽量一次并行搜索，最后一轮必须给出结论。仅输出建议，不得声称执行了修复。"
                    "代码固定为 snapshot 指定版本，官网文档可能比代码更新。缺少快照、检索无结果或存在版本差异时如实说明，不编造源码依据。"
                    "reply 先回答用户，再最多追问两个问题。根据用户已经提供的信息整理草稿，缺失信息不要编造。用户确认后才会提交。整体不超过1000字。"
                )
            targets = resolve_model_targets(db, "requirement_triage")
            if not targets:
                raise RuntimeError("No analysis model configured")
            with chat_budget(subject, user is None):
                text = dsh.run_with_fallback(targets, json.dumps(prompt, ensure_ascii=False), **({"knowledge": knowledge} if knowledge is not None else {}))
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            result = IntakeReply.model_validate_json(text)
            if payload.mode == "consultation":
                result.draft = None
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(503, "AI 暂时无法完成分析，请稍后重试或使用表单提交")
    result.reply = re.sub(r"deepseek(?:[-\s]+harness)?|\bdsh\b", "行影集 AI 助手", result.reply, flags=re.I)
    data = result.model_dump()
    history = (previous["history"] + [{"user": payload.content[:600], "assistant": result.reply[:800]}])[-3:]
    count = previous["count"] + 1
    state = jwt.encode({"sub": subject, "key": digest(x_intake_key), "aud": "feedback-intake",
                        "exp": utcnow() + timedelta(days=1), "history": history, "count": count,
                        "draft": data["draft"], "topic_established": bool(previous.get("topic_established") or allowed)}, settings.jwt_secret, algorithm="HS256")
    return ok({**data, "state": state, "quota": quota_view(db, subject, user is None, count),
               "sources": list(knowledge.sources.values()) if allowed and knowledge else [],
               "snapshot": knowledge.snapshot if allowed and knowledge else None})
