import hmac
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import UUID

from .collaboration_models import AIChatActivity
from .config import settings

# Only server-generated IDs cross the model gateway boundary; never store credentials.
conversation_usage: ContextVar[tuple[str, str, str | None] | None] = ContextVar("conversation_usage", default=None)


@contextmanager
def track_conversation(kind: str, conversation_id: str, message_id: str | None = None):
    token = conversation_usage.set((kind, conversation_id, message_id))
    try:
        yield
    finally:
        conversation_usage.reset(token)



def record_chat(db, kind: str, conversation_id: str, principal: str, *, retry: bool = False):
    anonymous = not principal.startswith("user:")
    subject = conversation_id if anonymous else principal
    actor_key = hmac.digest(settings.jwt_secret.encode(), f"ai-dashboard-actor:{subject}".encode(), "sha256").hex()
    db.add(AIChatActivity(kind=kind, conversation_id=conversation_id, actor_key=actor_key, anonymous=anonymous, retry=retry))



def intake_id(principal: str, browser_key: str) -> str:
    # Stable even when the first request fails before returning signed history.
    value = hmac.digest(settings.jwt_secret.encode(), f"ai-intake-usage:{principal}:{browser_key}".encode(), "sha256")
    return str(UUID(bytes=value[:16]))
