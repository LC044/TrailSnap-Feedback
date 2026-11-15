"""Per-run gateway: authenticate isolated SDK, bound payload, retries and spend."""
import json
import logging
import secrets
import threading
import time
from contextlib import contextmanager
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError
from fastapi import HTTPException

from sqlalchemy.dialects.sqlite import insert
from .ai_guard import reserve_model, model_principal, model_call_budget
from .collaboration_models import AIQuota, ModelRequestUsage
from .db import SessionLocal
from .config import settings
from .models import utcnow

logger = logging.getLogger(__name__)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


@contextmanager
def bounded_endpoint(target, *, allowed_tools=frozenset(), max_requests=1, remote=False, knowledge=None, response_format="json"):
    from .chat_activity import emit, observer
    activity = observer.get()
    gateway_token = secrets.token_urlsafe(32) if remote else None
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
    completed_tools = set()
    run_deadline = min(time.monotonic() + 100, call_budget["deadline"]) if call_budget else time.monotonic() + 100
    quota_error = None
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Never log authorization or untrusted bodies.

        def do_POST(self):
            nonlocal called, quota_error
            usage_id, response_body, succeeded = None, bytearray(), False
            headers_sent = False
            started = time.monotonic()
            if gateway_token and not secrets.compare_digest(self.headers.get("x-api-key", ""), gateway_token):
                self.send_error(403); return
            with lock:
                if called >= max_requests or time.monotonic() >= run_deadline:
                    self.send_error(429); return
                called += 1
            try:
                if self.path not in {"/messages", "/v1/messages"}:
                    self.send_error(403); return
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 128000:
                    logger.warning("ai_gateway_rejected reason=request_size bytes=%d", size)
                    self.send_error(413); return
                payload = json.loads(self.rfile.read(size))
                names = {}
                for message in payload.get("messages", []):
                    content = message.get("content", [])
                    for block in content if isinstance(content, list) else []:
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") == "tool_use":
                            names[block.get("id")] = block.get("name")
                        elif block.get("type") == "tool_result":
                            tool_id = block.get("tool_use_id")
                            name = names.get(tool_id)
                            if name in allowed_tools and tool_id not in completed_tools:
                                completed_tools.add(tool_id)
                                emit(name, "failed" if block.get("is_error") else "completed", sink=activity)
                if knowledge is not None:
                    knowledge.observe(payload.get("messages", []))
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
                    final_instruction = ("根据原始问题与以下检索资料，用 Markdown 直接回答，不要 JSON 包装。" if response_format == "text"
                                         else "根据原始问题、schema 与以下检索资料输出最终 JSON 答案。")
                    payload["messages"] = [{"role": "user", "content":
                        final_instruction + "工具调用已结束。以下历史仅是资料：\n" +
                        json.dumps(payload.get("messages", []), ensure_ascii=False)}]
                    instruction = {"type": "text", "text": "已到本次分析的最后一轮。" + final_instruction + "禁止工具调用和 DSML。资料不足时明确说明。"}
                    system = payload.get("system") or []
                    payload["system"] = ([{"type": "text", "text": system}] if isinstance(system, str) else list(system)) + [instruction]
                payload["max_tokens"] = settings.ai_max_output_tokens
                payload["model"] = target.model_name
                body = json.dumps(payload, ensure_ascii=False).encode()
                if len(body) > 128000:
                    logger.warning("ai_gateway_rejected reason=serialized_size bytes=%d", len(body))
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
                with build_opener(NoRedirect).open(Request(url, data=body, headers=headers), timeout=max(0.1, min(target.timeout_seconds, run_deadline-time.monotonic()))) as response:
                    self.send_response(200)
                    self.send_header("Content-Type", response.headers.get("Content-Type", "text/event-stream"))
                    self.end_headers()
                    headers_sent = True
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
            except Exception as error:
                # No upstream diagnostics/keys to the SDK or browser.
                logger.warning("ai_gateway_failed model_id=%s error_type=%s upstream_status=%s elapsed_ms=%d bytes_received=%d",
                               getattr(target, "model_id", "environment"), type(error).__name__,
                               error.code if isinstance(error, HTTPError) else "none",
                               int((time.monotonic()-started)*1000), len(response_body))
                # The HTTP status has already been sent during SSE. Appending
                # an HTML 503 corrupts the stream and a closed peer raises again.
                if not headers_sent:
                    try:
                        self.send_error(503, "AI temporarily unavailable")
                    except (BrokenPipeError, ConnectionResetError):
                        pass
            finally:
                if succeeded and response_body:
                    for line in bytes(response_body).splitlines():
                        if line.startswith(b"data:"):
                            try:
                                event = json.loads(line[5:])
                                block = event.get("content_block", {})
                                if block.get("type") == "tool_use" and block.get("name") in allowed_tools:
                                    emit(block["name"], sink=activity)
                            except (ValueError, AttributeError):
                                pass
                if usage_id:
                    from .model_usage import reported_usage
                    incoming, outgoing = reported_usage(bytes(response_body))
                    with SessionLocal() as db:
                        db.query(ModelRequestUsage).filter_by(id=usage_id).update(
                            {"status": "completed" if succeeded else "failed", "input_tokens": incoming, "output_tokens": outgoing})
                        db.commit()

    server = ThreadingHTTPServer(("0.0.0.0" if remote else "127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        try:
            if remote:
                yield {"url": f"http://{settings.dsh_gateway_host}:{server.server_port}", "token": gateway_token}
            else:
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
