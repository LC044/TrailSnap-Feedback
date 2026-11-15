"""Transactional notifications. SMTP delivery is at least once, never exactly once."""
import secrets
import smtplib
import ssl
from datetime import timedelta
from email.message import EmailMessage

from jose import JWTError, jwt
from sqlalchemy import and_, or_

from .config import settings
from .collaboration_models import EmailDelivery, EmailSubscription
from .models import ReleaseBatchItem, Requirement, RequirementFollower, User, new_id, utcnow


def subscription_token(subscription_id, purpose, version=None):
    if version is None:
        from .db import SessionLocal
        with SessionLocal() as db:
            version = db.get(EmailSubscription, subscription_id).token_version
    return jwt.encode({"sub": subscription_id, "version": version, "purpose": purpose, "exp": utcnow() + timedelta(days=3650 if purpose == "unsubscribe" else 30)}, settings.jwt_secret, algorithm="HS256")


def decode_subscription_token(token, purpose, db):
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        if payload.get("purpose") != purpose:
            raise ValueError("Invalid purpose")
        row = db.get(EmailSubscription, payload['sub'])
        if not row or payload.get('version') != row.token_version:
            raise ValueError("链接已失效，请重新订阅")
        return payload["sub"]
    except (JWTError, KeyError) as exc:
        raise ValueError("链接已失效，请重新订阅") from exc


def subscribe(db, requirement, email):
    from .ai_guard import consume, digest
    email = str(email).strip().lower()
    row = db.query(EmailSubscription).filter_by(requirement_id=requirement.id, email=email).first()
    if row and row.active:
        return row
    consume(db, f"mail:{digest(email)}", 3, 86400)
    consume(db, "mail-global", 100, 86400)
    if not row and db.query(EmailSubscription).filter_by(requirement_id=requirement.id).count() >= 3:
        from fastapi import HTTPException
        raise HTTPException(429, "每条需求最多订阅 3 个邮箱")
    if row:
        row.active, row.verified = True, False
        row.token_version = new_id()
    else:
        row = EmailSubscription(id=new_id(), requirement_id=requirement.id, email=email)
        db.add(row)
    db.flush()
    link = settings.public_url("notifications/verify") + "#token=" + subscription_token(row.id, "verify", row.token_version)
    db.add(EmailDelivery(subscription_id=row.id, event_key=f"verify:{row.id}:{new_id()}", kind="verify",
                         subject="行影集：确认需求通知邮箱", body=f"你申请订阅行影集的需求进度。请打开链接后点击确认：\n{link}\n\n若不是你本人操作，请忽略此邮件。"))
    return row


def event_notifications(db, event):
    """Called before the business transaction commits; never contacts SMTP."""
    requirement_ids = []
    if event.object_type == "requirement" and event.action in {
        "requirement.created", "requirement.updated", "requirement.status_changed", "requirement.reviewed",
        "triage.completed", "consultation.created", "requirement.supplement_added",
    }:
        requirement_ids = [event.object_id]
    elif event.action == "release_batch.status_changed" and event.details.get("after") == "published" and event.details.get("before") != "published":
        requirement_ids = [r[0] for r in db.query(ReleaseBatchItem.requirement_id).filter_by(batch_id=event.object_id).all()]
    elif event.action == "release_batch.delivery_status" and event.details.get("status") == "completed":
        item = db.get(ReleaseBatchItem, event.details.get("item_id"))
        requirement_ids = [item.requirement_id] if item else []
    for requirement_id in requirement_ids:
        requirement = db.get(Requirement, requirement_id)
        if not requirement or requirement.deleted_at:
            continue
        for subscription in db.query(EmailSubscription).filter_by(requirement_id=requirement_id, active=True, verified=True).all():
            # Mail carries a neutral event notice; private content is read only after web authorization.
            kind = "consultation" if event.action == "consultation.created" else "release" if event.details.get("after") in {"published", "released"} else "completed" if event.details.get("after") == "release_ready" or event.details.get("status") == "completed" else "changed"
            labels = {"consultation": "有待讨论的问题", "release": "已发布", "completed": "已实现，等待发布", "changed": "有新进展"}
            link = settings.public_url(f"requirements/REQ-{requirement.public_number}/conversation")
            if requirement.created_by is None:
                link += "#conversation_token=" + subscription_token(subscription.id, "conversation", subscription.token_version)
            unsubscribe = settings.public_url("notifications/unsubscribe") + "#token=" + subscription_token(subscription.id, "unsubscribe", subscription.token_version)
            db.add(EmailDelivery(subscription_id=subscription.id, event_key=f"{event.id}:{subscription.id}", kind=kind,
                                 subject=f"行影集 REQ-{requirement.public_number} {labels[kind]}",
                                 body=f"你订阅的 REQ-{requirement.public_number} {labels[kind]}。\n查看进度或继续讨论：{link}\n\n退订：{unsubscribe}"))


def claim_email(db):
    now = utcnow()
    eligible = and_(EmailDelivery.available_at <= now, or_(EmailDelivery.status == "queued", and_(EmailDelivery.status == "sending", EmailDelivery.lease_expires_at < now)))
    candidate = db.query(EmailDelivery.id).filter(eligible).order_by(EmailDelivery.created_at).first()
    if not candidate:
        return None
    token = secrets.token_hex(24)
    claimed = db.query(EmailDelivery).filter(EmailDelivery.id == candidate.id, eligible).update({
        "status": "sending", "lease_token": token, "lease_expires_at": now + timedelta(minutes=5), "attempts": EmailDelivery.attempts + 1,
    }, synchronize_session=False)
    db.commit()
    return (candidate.id, token) if claimed else None


def send_email(db, delivery_id, lease_token):
    row = db.query(EmailDelivery).filter_by(id=delivery_id, status="sending", lease_token=lease_token).first()
    if not row:
        return
    subscription = db.get(EmailSubscription, row.subscription_id)
    if not subscription or not subscription.active or (row.kind != "verify" and not subscription.verified):
        row.status = "cancelled"
        db.commit()
        return
    try:
        from .mail_settings import sender_pool, sender_password
        accounts = sender_pool(db, settings)
        if not accounts:
            raise RuntimeError("SMTP 尚未配置")
        from .ai_guard import consume, digest
        consume(db, f"mail-send:{digest(subscription.email)}", 20, 86400)
        consume(db, "mail-send-global", 1000, 86400)
        db.commit()
        delivered = False
        for account in accounts:
            # Each account is tried at most once per delivery attempt. Failed
            # attempts also consume its daily budget to avoid retry storms.
            try:
                with db.begin_nested():
                    consume(db, "smtp-account:" + account["id"], account["daily_limit"], 86400)
                db.commit()
                message = EmailMessage()
                message["From"], message["To"], message["Subject"] = account["sender"], subscription.email, row.subject
                message["Message-ID"] = f"<{row.id}@{settings.web_url.split('://')[-1].split('/')[0].split(':')[0]}>"
                message.set_content(row.body)
                if account["tls"] not in {"ssl", "starttls", "none"}:
                    raise RuntimeError("Invalid TLS mode")
                cls = smtplib.SMTP_SSL if account["tls"] == "ssl" else smtplib.SMTP
                with cls(account["host"], account["port"], timeout=5) as smtp:
                    if account["tls"] == "starttls":
                        smtp.starttls(context=ssl.create_default_context())
                    if account["username"]:
                        smtp.login(account["username"], sender_password(account))
                    smtp.send_message(message)
                delivered = True
                break
            except Exception:
                db.rollback()
        if not delivered:
            raise RuntimeError("所有发件账号均不可用或已达限额")
        updates = {"status": "sent", "sent_at": utcnow(), "last_error": None}
    except Exception:
        # Do not put SMTP credentials, recipients, or provider response bodies in public logs.
        updates = {"status": "failed" if row.attempts >= settings.max_job_attempts else "queued",
                   "last_error": "所有发件账号发送失败或已达限额，请检查邮件设置", "available_at": utcnow() + timedelta(seconds=min(3600, 30 * 2 ** row.attempts))}
    updates.update(lease_expires_at=None, lease_token=None)
    db.query(EmailDelivery).filter_by(id=delivery_id, lease_token=lease_token).update(updates, synchronize_session=False)
    db.commit()
