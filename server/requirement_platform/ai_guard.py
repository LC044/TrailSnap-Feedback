"""Server-owned quotas. No model decision grants permissions or extra budget."""
import hashlib
import re
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.dialects.sqlite import insert

from .collaboration_models import AIQuota
from .config import settings
from .quota_policy import read_policy

model_principal = ContextVar("model_principal", default=None)
model_call_budget = ContextVar("model_call_budget", default=None)


@contextmanager
def chat_budget(principal, anonymous):
    token = model_principal.set((principal, anonymous))
    try:
        yield
    finally:
        model_principal.reset(token)


REFUSAL = "我只能讨论行影集的使用、需求和问题反馈。请描述行影集中遇到的问题或希望改进的功能。"
# This filter is an inexpensive first layer, not the permission boundary.
UNSAFE = re.compile(r"忽略.{0,12}(指令|规则|提示)|泄露.{0,12}(提示|密钥)|系统提示词|越狱|ignore.{0,30}(instruction|rule)|system prompt|jailbreak|扮演.{0,15}(无限制|其他)|挖矿|色情|代写.{0,8}(论文|作业)|天气预报|股票推荐|写.{0,8}(首诗|小说|论文)|write.{0,12}(poem|essay)", re.I)
RELATED = re.compile(r"行影集|trailsnap|需求|照片|相册|轨迹|导出|导入|上传|登录|地图|复现|闪退|补丁|修复|预期|场景|信息|问题|手机|桌面|同步|版本|报错|设置|功能|通知|bug|photo|album|export|crash|requirement", re.I)


def permitted_topic(text, context=""):
    # Context must come from signed intake state or the authorized requirement,
    # never from an unsigned client-supplied history. Short answers inherit it.
    return not UNSAFE.search(text) and bool(RELATED.search(text) or RELATED.search(context))


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()[:40]


def bucket(scope, seconds):
    now = int(time.time())
    end = (now // seconds + 1) * seconds
    return f"{scope}:{now // seconds}", datetime.fromtimestamp(end, timezone.utc), end - now


def consume(db, scope, limit, seconds, amount=1):
    key, expiry, wait = bucket(scope, seconds)
    db.execute(insert(AIQuota).values(key=key, used=0, expires_at=expiry).on_conflict_do_nothing())
    changed = db.query(AIQuota).filter(AIQuota.key == key, AIQuota.used + amount <= limit).update(
        {"used": AIQuota.used + amount}, synchronize_session=False)
    if not changed:
        raise HTTPException(429, "已达到使用限额，请稍后再试", headers={"Retry-After": str(wait)})


def quota_view(db, principal, anonymous, count):
    policy = read_policy(db)
    limit = policy.anonymous_daily if anonymous else policy.user_daily
    key, _, wait = bucket(f"chat:{digest(principal)}", 86400)
    row = db.get(AIQuota, key, populate_existing=True)
    used = row.used if row else 0
    pace = db.get(AIQuota, f"pace:{digest(principal)}")
    cooldown = max(0, int(pace.expires_at.replace(tzinfo=timezone.utc).timestamp() - time.time()) + 1) if pace else 0
    token_limit = policy.anonymous_tokens if anonymous else policy.user_tokens
    token_key, _, _ = bucket(f"chat-tokens:{digest(principal)}", 86400)
    token_row = db.get(AIQuota, token_key, populate_existing=True)
    tokens = token_row.used if token_row else 0
    def scope_used(scope):
        row = db.get(AIQuota, bucket(scope, 86400)[0], populate_existing=True)
        return row.used if row else 0
    global_exhausted = (scope_used("chat-global") >= policy.global_daily or scope_used("model-calls") >= policy.global_daily
                        or scope_used("model-reserved-tokens") + settings.ai_max_output_tokens >= policy.global_tokens)
    return {"daily_used": used, "daily_limit": limit, "daily_remaining": max(0, limit-used),
            "limit_mode": policy.mode, "tokens_used": tokens, "tokens_limit": token_limit,
            "tokens_remaining": max(0, token_limit-tokens),
            "global_exhausted": global_exhausted,
            "exhausted": global_exhausted or (policy.mode != "tokens" and used >= limit) or (policy.mode != "count" and tokens >= token_limit),
            "conversation_used": count, "conversation_limit": 100,
            "interval_seconds": policy.interval_seconds, "retry_after_seconds": cooldown, "reset_after_seconds": wait}


def admit_chat(db, principal, ip, anonymous):
    from datetime import timedelta
    policy = read_policy(db)
    if quota_view(db, principal, anonymous, 0)["exhausted"]:
        raise HTTPException(429, "今日对话额度已用完", headers={"Retry-After": str(bucket('chat', 86400)[2])})
    now = datetime.now(timezone.utc)
    key = f"pace:{digest(principal)}"
    db.execute(insert(AIQuota).values(key=key, used=0, expires_at=now).on_conflict_do_nothing())
    changed = db.query(AIQuota).filter(AIQuota.key == key, AIQuota.expires_at <= now).update(
        {"expires_at": now + timedelta(seconds=policy.interval_seconds)}, synchronize_session=False)
    if not changed:
        raise HTTPException(429, f"发送过于频繁，请在 {policy.interval_seconds} 秒后重试", headers={"Retry-After": str(policy.interval_seconds)})
    limit = policy.anonymous_daily if anonymous else policy.user_daily
    consume(db, f"chat:{digest(principal)}", limit if policy.mode != "tokens" else 1000000000, 86400)
    consume(db, f"ip-chat:{digest(ip)}", policy.ip_daily, 86400)
    consume(db, "chat-global", policy.global_daily, 86400)


def reserve_model(db, request_bytes, principal=None):
    # UTF-8 bytes conservatively bound input tokens; charge failures too. No refund.
    policy = read_policy(db)
    amount = request_bytes + settings.ai_max_output_tokens
    consume(db, "model-calls", policy.global_daily, 86400)
    consume(db, "model-reserved-tokens", policy.global_tokens, 86400, amount)
    if principal:
        subject, anonymous = principal
        limit = policy.anonymous_tokens if anonymous else policy.user_tokens
        consume(db, f"chat-tokens:{digest(subject)}", limit if policy.mode != "count" else 1000000000, 86400, amount)
