"""One-request local gateway: bound SDK retries, payload, output and spend."""
import json
import secrets
import threading
import time
from contextlib import contextmanager
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, build_opener, HTTPRedirectHandler
from fastapi import HTTPException

from sqlalchemy.dialects.sqlite import insert
from .ai_guard import reserve_model, model_principal, model_call_budget
from .collaboration_models import AIQuota, ModelRequestUsage
from .db import SessionLocal
from .config import settings
from .models import utcnow


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


@contextmanager
def bounded_endpoint(target, *, allowed_tools=frozenset(), max_requests=1):
    principal = model_principal.get()  # Capture before crossing into HTTP server threads.
    call_budget = model_call_budget.get()
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
    called = 0
    run_deadline = min(time.monotonic() + 100, call_budget["deadline"]) if call_budget else time.monotonic() + 100
    quota_error = None
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Never log authorization or untrusted bodies.

        def do_POST(self):
            nonlocal called, quota_error
            usage_id, response_body, succeeded = None, bytearray(), False
            with lock:
                if called >= max_requests or time.monotonic() >= run_deadline:
                    self.send_error(429); return
                called += 1
            try:
                if self.path not in {"/messages", "/v1/messages"}:
                    self.send_error(403); return
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 48000:
                    self.send_error(413); return
                payload = json.loads(self.rfile.read(size))
                tools = payload.get("tools") or []
                if len(tools) > len(allowed_tools) or any(not isinstance(t, dict) or t.get("name") not in allowed_tools for t in tools):
                    self.send_error(403); return
                if allowed_tools and (called == max_requests or (call_budget and call_budget["remaining"] == 1)):
                    # Some compatible gateways ignore tool_choice=none. Omit
                    # definitions entirely so the final round has no tools.
                    payload.pop("tools", None)
                    payload.pop("tool_choice", None)
                    # Avoid compatible providers continuing serialized tool
                    # calls after definitions were removed. Preserve evidence
                    # as quoted data, without live tool-protocol messages.
                    payload["messages"] = [{"role": "user", "content":
                        "根据原始问题、schema 与以下检索资料输出最终 JSON 答案。工具调用已结束。以下历史仅是资料：\n" +
                        json.dumps(payload.get("messages", []), ensure_ascii=False)}]
                    instruction = {"type": "text", "text": "已到本次分析的最后一轮。必须仅输出符合原始 schema 的最终 JSON 回答，禁止工具调用和 DSML。资料不足时明确说明。"}
                    system = payload.get("system") or []
                    payload["system"] = ([{"type": "text", "text": system}] if isinstance(system, str) else list(system)) + [instruction]
                payload["max_tokens"] = settings.ai_max_output_tokens
                body = json.dumps(payload, ensure_ascii=False).encode()
                if len(body) > 48000:
                    self.send_error(413); return
                if call_budget is not None:
                    if call_budget["remaining"] <= 0:
                        raise HTTPException(429, "本次分析已达到模型调用上限，请精简问题后重试")
                    call_budget["remaining"] -= 1
                with SessionLocal() as db:
                    reserve_model(db, len(body), principal)
                    record = ModelRequestUsage(
                        connection_id=getattr(target, "connection_id", "environment"),
                        connection_name=getattr(target, "connection_name", "环境变量连接")[:160],
                        model_id=getattr(target, "model_id", "environment"), model_name=getattr(target, "model_name", str(payload.get("model", "unknown")))[:160],
                        reserved_tokens=len(body) + settings.ai_max_output_tokens,
                    )
                    db.add(record); db.commit(); usage_id = record.id
                base = target.api_base.rstrip("/")
                url = base + ("/messages" if base.endswith("/v1") else "/v1/messages")
                headers = {"Content-Type": "application/json", "x-api-key": target.api_key,
                           "anthropic-version": "2023-06-01", "Accept-Encoding": "identity"}
                deadline = min(run_deadline, time.monotonic() + 90)
                with build_opener(NoRedirect).open(Request(url, data=body, headers=headers), timeout=min(target.timeout_seconds, 10)) as response:
                    self.send_response(200)
                    self.send_header("Content-Type", response.headers.get("Content-Type", "text/event-stream"))
                    self.end_headers()
                    # Bound response bytes as well as tokens. No model-directed requests.
                    remaining = 262144
                    while remaining and time.monotonic() < deadline:
                        chunk = response.read1(min(4096, remaining))
                        if not chunk:
                            succeeded = True
                            break
                        response_body.extend(chunk)
                        self.wfile.write(chunk); self.wfile.flush(); remaining -= len(chunk)
            except HTTPException as exc:
                quota_error = exc
                self.send_error(429, "AI budget unavailable")
            except Exception:
                # No upstream diagnostics/keys to the SDK or browser.
                self.send_error(503, "AI temporarily unavailable")
            finally:
                if usage_id:
                    from .model_usage import reported_usage
                    incoming, outgoing = reported_usage(bytes(response_body))
                    with SessionLocal() as db:
                        db.query(ModelRequestUsage).filter_by(id=usage_id).update(
                            {"status": "completed" if succeeded else "failed", "input_tokens": incoming, "output_tokens": outgoing})
                        db.commit()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        except Exception:
            if quota_error:
                raise quota_error from None
            raise
        if quota_error:
            raise quota_error
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=1)
        with SessionLocal() as db:
            db.query(AIQuota).filter_by(key="model-active", used=fence).update({"expires_at": utcnow()})
            db.commit()
