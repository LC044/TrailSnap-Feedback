"""One-request local gateway: bound SDK retries, payload, output and spend."""
import json
import secrets
import threading
import time
from contextlib import contextmanager
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from sqlalchemy.dialects.sqlite import insert
from .ai_guard import reserve_model
from .collaboration_models import AIQuota
from .db import SessionLocal
from .config import settings
from .models import utcnow


@contextmanager
def bounded_endpoint(target):
    # One global in-flight request across workers/replicas sharing the SQLite volume.
    fence = secrets.randbelow(2**30) + 1
    with SessionLocal() as db:
        now = utcnow()
        db.execute(insert(AIQuota).values(key="model-active", used=0, expires_at=now).on_conflict_do_nothing())
        claimed = db.query(AIQuota).filter(AIQuota.key == "model-active", AIQuota.expires_at <= now).update(
            {"used": fence, "expires_at": now + timedelta(seconds=150)}, synchronize_session=False)
        db.commit()
        if not claimed:
            raise RuntimeError("AI 正忙，请稍后重试")
    lock = threading.Lock()
    called = False
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Never log authorization or untrusted bodies.

        def do_POST(self):
            nonlocal called
            with lock:
                if called:
                    self.send_error(429); return
                called = True
            try:
                if self.path not in {"/messages", "/v1/messages"}:
                    self.send_error(403); return
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 48000:
                    self.send_error(413); return
                payload = json.loads(self.rfile.read(size))
                if payload.get("tools"):
                    self.send_error(403); return
                payload["max_tokens"] = settings.ai_max_output_tokens
                body = json.dumps(payload, ensure_ascii=False).encode()
                if len(body) > 48000:
                    self.send_error(413); return
                with SessionLocal() as db:
                    reserve_model(db, len(body)); db.commit()
                base = target.api_base.rstrip("/")
                url = base + ("/messages" if base.endswith("/v1") else "/v1/messages")
                headers = {"Content-Type": "application/json", "x-api-key": target.api_key,
                           "anthropic-version": "2023-06-01", "Accept-Encoding": "identity"}
                deadline = time.monotonic() + 90
                with urlopen(Request(url, data=body, headers=headers), timeout=min(target.timeout_seconds, 10)) as response:
                    self.send_response(200)
                    self.send_header("Content-Type", response.headers.get("Content-Type", "text/event-stream"))
                    self.end_headers()
                    # Bound response bytes as well as tokens. No model-directed requests.
                    remaining = 262144
                    while remaining and time.monotonic() < deadline:
                        chunk = response.read1(min(4096, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk); self.wfile.flush(); remaining -= len(chunk)
            except Exception:
                # No upstream diagnostics/keys to the SDK or browser.
                self.send_error(503, "AI temporarily unavailable")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=1)
        with SessionLocal() as db:
            db.query(AIQuota).filter_by(key="model-active", used=fence).update({"expires_at": utcnow()})
            db.commit()
