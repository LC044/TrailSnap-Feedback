"""Encrypted sender pool. Empty managed configuration explicitly disables mail."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy.orm import Session

from .ai_settings import encrypt_api_key, decrypt_api_key
from .collaboration_models import AIQuota, MailSettings
from .config import settings
from .db import get_db
from .models import User, new_id
from .security import manager
from .api.responses import ok

router = APIRouter(prefix="/api/admin/mail-settings", tags=["mail-settings"])


class SenderInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: str | None = Field(default=None, max_length=36)
    name: str = Field(min_length=1, max_length=60)
    host: str = Field(min_length=1, max_length=253, pattern=r"^[A-Za-z0-9.-]+$")
    port: int = Field(default=465, ge=1, le=65535)
    username: str = Field(default="", max_length=255)
    password: str | None = Field(default=None, max_length=1000)
    sender: EmailStr
    tls: str = Field(default="ssl", pattern=r"^(ssl|starttls|none)$")
    enabled: bool = True
    daily_limit: int = Field(default=100, ge=1, le=10000)

    @field_validator("name", "username", "password")
    @classmethod
    def no_newlines(cls, value):
        if value and any(c in value for c in "\r\n\x00"):
            raise ValueError("不能包含换行")
        return value


class MailInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accounts: list[SenderInput] = Field(max_length=8)


def environment_account(config=settings):
    if not config.smtp_host or not config.smtp_from:
        return []
    return [dict(id="environment", name="环境变量发件账号", host=config.smtp_host,
                 port=config.smtp_port, username=config.smtp_username, password=config.smtp_password,
                 sender=config.smtp_from, tls=config.smtp_tls, enabled=True, daily_limit=1000)]


def sender_pool(db, config=settings):
    """Reserve one rotation position durably before contacting any provider."""
    row = db.get(MailSettings, 1)
    if row is None:
        return environment_account(config)
    db.query(MailSettings).filter_by(id=1).update(
        {"cursor": MailSettings.cursor + 1}, synchronize_session=False)
    # RETURNING is not required; the write lock serializes this read on SQLite.
    db.refresh(row)
    accounts = [dict(a) for a in row.accounts if a["enabled"]]
    start = (row.cursor - 1) % len(accounts) if accounts else 0
    return accounts[start:] + accounts[:start]


@router.get("")
def read_settings(actor: User = Depends(manager), db: Session = Depends(get_db)):
    row = db.get(MailSettings, 1)
    accounts = row.accounts if row else environment_account()
    safe = []
    for account in accounts:
        value = {k: v for k, v in account.items() if k not in {"password", "password_encrypted"}}
        value["has_password"] = bool(account.get("password_encrypted") or account.get("password"))
        from .ai_guard import bucket
        quota = db.get(AIQuota, bucket("smtp-account:" + account["id"], 86400)[0])
        from .models import utcnow
        value["used_today"] = quota.used if quota and quota.expires_at.replace(tzinfo=None) > utcnow().replace(tzinfo=None) else 0
        safe.append(value)
    return ok({"source": "managed" if row else "environment", "accounts": safe})


@router.put("")
def save_settings(payload: MailInput, actor: User = Depends(manager), db: Session = Depends(get_db)):
    row = db.get(MailSettings, 1)
    old = {a["id"]: a for a in row.accounts} if row else {a["id"]: a for a in environment_account()}
    ids = [a.id for a in payload.accounts if a.id]
    if len(ids) != len(set(ids)) or any(i not in old for i in ids):
        raise HTTPException(422, "发件账号已改变，请刷新设置")
    accounts = []
    for value in payload.accounts:
        account = value.model_dump(exclude={"password"})
        prior = old.get(value.id, {})
        account["id"] = value.id if value.id != "environment" else None
        account["id"] = account["id"] or new_id()
        secret = value.password if value.password is not None else prior.get("password")
        account["password_encrypted"] = encrypt_api_key(secret)[0] if secret is not None else prior.get("password_encrypted")
        if account["username"] and not account["password_encrypted"]:
            raise HTTPException(422, "请填写发件账号授权码")
        accounts.append(account)
    if row is None:
        row = MailSettings(id=1, cursor=0)
        db.add(row)
    row.accounts = accounts
    db.commit()
    return read_settings(actor, db)


def sender_password(account):
    return account.get("password", "") if "password" in account else decrypt_api_key(account.get("password_encrypted"))
