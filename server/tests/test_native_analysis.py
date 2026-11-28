import json
import sys
import threading
from contextlib import nullcontext
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from requirement_platform import dsh, knowledge, native_runtime
from requirement_platform.db import init_db
from test_readonly_knowledge import indexed


def test_citations_only_from_successful_native_results(indexed):
    reader = knowledge.ReadOnlyKnowledge()
    assert reader._manifest is None
    call = {"type": "tool_use", "id": "read-1", "name": "read", "input": {"file_path": "source/package/server/export.py", "offset": 2}}
    messages = [{"role": "assistant", "content": [call]}]
    reader.observe(messages)
    assert not reader.sources
    messages.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": "read-1", "is_error": True, "content": "not found"}]})
    reader.observe(messages)
    assert not reader.sources
    messages[-1]["content"][0].update(is_error=False, content="2: source")
    reader.observe(messages)
    assert list(reader.sources.values())[0]["url"].endswith("export.py#L2")
    assert not hasattr(reader, "execute")  # No platform keyword search implementation.


@pytest.mark.parametrize("effort,expected", [("none", "none"), ("high", "high")])
def test_platform_uses_isolated_runner_without_provider_key(indexed, monkeypatch, effort, expected):
    calls = []
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return httpx.Response(200, json={"reply": "分析完成"}, request=httpx.Request("POST", url))
    monkeypatch.setattr(dsh.httpx, "Client", Client)
    monkeypatch.setattr(dsh, "settings", replace(dsh.settings, dsh_runner_url="http://runner", dsh_runner_token="runner-auth"))
    monkeypatch.setattr(dsh, "bounded_endpoint", lambda *_a, **_kw: nullcontext({"url": "http://api:12345", "token": "one-run-token"}))
    target = SimpleNamespace(model_name="configured-model", api_key="REAL-PROVIDER-SECRET", reasoning_effort=effort, timeout_seconds=45)
    assert dsh.run_harness(target, "{}") == "分析完成"
    body = calls[0][1]["json"]
    assert body["reasoning_effort"] == expected
    assert body["timeout"] == 100
    assert body["request_timeout"] == 45
    assert body["gateway_token"] == "one-run-token" and body["generation"]
    assert "REAL-PROVIDER-SECRET" not in json.dumps(calls)


def test_no_local_full_access_fallback(monkeypatch):
    monkeypatch.setattr(dsh, "settings", replace(dsh.settings, dsh_runner_url="", dsh_runner_token=""))
    with pytest.raises(RuntimeError, match="隔离"):
        dsh.run_harness(object(), "{}")


@pytest.mark.parametrize("effort,expected", [("none", "off"), ("minimal", "low"), ("medium", "low"), ("high", "high"), ("xhigh", "max")])
def test_native_runtime_preserves_reasoning_and_clears_inherited_secrets(tmp_path, monkeypatch, effort, expected):
    import deepseek_harness
    calls = []
    class Harness:
        def __init__(self, **kwargs): calls.append(kwargs)
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def close(self): pass
        def run(self, *_): return SimpleNamespace(finish_reason="completed", final_response="完成")
    monkeypatch.setattr(deepseek_harness, "DeepSeekHarness", Harness)
    monkeypatch.setenv("RP_SMTP_PASSWORD", "must-not-inherit")
    payload = dict(system=dsh.SYSTEM_PROMPT, model="test", gateway_url="http://api:12345", gateway_token="ephemeral",
                   reasoning_effort=effort, max_tokens=1024, prompt="{}", timeout=100, request_timeout=45)
    assert native_runtime.run(payload, tmp_path) == "完成"
    assert calls[0]["reasoning_effort"] == expected
    assert calls[0]["env"]["RP_SMTP_PASSWORD"] == ""
    assert calls[0]["api_key"] == "ephemeral"
    assert calls[0]["request_timeout_seconds"] == 45


def test_remote_gateway_auth_precedes_budget_and_reports_native_completion(indexed, monkeypatch):
    from requirement_platform import model_gateway, chat_activity
    reserved, events = [], []
    image = {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "ZmFrZQ=="}}
    monkeypatch.setattr(model_gateway, "reserve_model", lambda *_: reserved.append(True))
    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert body["model"] == "configured-model"
            text, media = body["messages"][0]["content"]
            assert text["type"] == "text" and "TrailSnap screenshot" in text["text"]
            assert media == image
            assert self.headers["x-api-key"] == "provider-only"
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(b'{"content":[{"type":"text","text":"done"}],"usage":{"input_tokens":10,"output_tokens":1}}')
    server = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    target = SimpleNamespace(model_name="configured-model", api_base=f"http://127.0.0.1:{server.server_port}", api_key="provider-only", timeout_seconds=5)
    marker = chat_activity.observer.set(events.append)
    try:
        with model_gateway.bounded_endpoint(target, remote=True, allowed_tools=native_runtime.NATIVE_TOOLS, max_requests=1, images=[image]) as gateway:
            port = gateway["url"].rsplit(":", 1)[1]
            url = f"http://127.0.0.1:{port}/v1/messages"
            call = {"type": "tool_use", "id": "read-test", "name": "read", "input": {"file_path": "source/test.py"}}
            payload = {"model": "test", "system": "public-source-evidence " * 3000, "messages": [{"role": "user", "content": "TrailSnap screenshot"}, {"role": "assistant", "content": [call]},
                       {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "read-test", "content": "source"}]}]}
            with httpx.Client(trust_env=False) as client:
                assert client.post(url, json={}).status_code == 403
                assert not reserved
                headers = {"x-api-key": gateway["token"]}
                assert client.post(url, json=payload, headers=headers).status_code == 200
                assert client.post(url, json={}, headers=headers).status_code == 429
            assert len(reserved) == 1
            assert events == [{"kind": "read", "label": chat_activity.LABELS["read"], "status": "completed"}]
    finally:
        chat_activity.observer.reset(marker)
        server.shutdown(); server.server_close()


def test_runner_cannot_use_public_platform_apis(monkeypatch):
    import asyncio
    from fastapi.testclient import TestClient
    from requirement_platform import runner_boundary
    from requirement_platform.main import app
    monkeypatch.setattr(runner_boundary, "settings", replace(runner_boundary.settings, dsh_runner_url="http://dsh-runner:8013"))
    async def addresses(*_args, **_kwargs):
        return [(2, 1, 6, "", ("10.0.0.5", 8013))]
    monkeypatch.setattr(asyncio.BaseEventLoop, "getaddrinfo", addresses)
    with TestClient(app, client=("10.0.0.5", 12345)) as runner:
        assert runner.get("/api/health").status_code == 403
        assert runner.post("/api/requirements", json={}).status_code == 403
    with TestClient(app, client=("10.0.0.6", 12345)) as user:
        assert user.get("/api/health").status_code == 200


def test_upstream_timeout_and_failure_logs_do_not_expose_diagnostics(indexed, monkeypatch, caplog):
    from uuid import uuid4
    from requirement_platform import model_gateway
    from requirement_platform.collaboration_models import ModelRequestUsage
    from requirement_platform.conversation_usage import track_conversation

    conversation_id, message_id = str(uuid4()), str(uuid4())
    monkeypatch.setattr(model_gateway, "reserve_model", lambda *_: None)
    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(503); self.end_headers()
            self.wfile.write(b'private-upstream-prompt-and-key')
    server = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    opener = model_gateway.build_opener
    timeouts = []
    class Opener:
        def open(self, request, *, timeout):
            timeouts.append(timeout)
            return opener(model_gateway.NoRedirect).open(request, timeout=timeout)
    monkeypatch.setattr(model_gateway, "build_opener", lambda *_: Opener())
    target = SimpleNamespace(model_name="test", api_base=f"http://127.0.0.1:{server.server_port}", api_key="private-provider-key", timeout_seconds=45)
    try:
        with track_conversation("requirement", conversation_id, message_id), model_gateway.bounded_endpoint(target) as url:
            response = httpx.post(url + "/v1/messages", json={"messages": []}, trust_env=False)
            assert response.status_code == 503
            assert "private" not in response.text
        with model_gateway.SessionLocal() as db:
            record = db.query(ModelRequestUsage).filter_by(conversation_id=conversation_id).one()
            assert (record.conversation_kind, record.message_id, record.status) == ("requirement", message_id, "failed")
        assert timeouts == [45]  # No hidden ten-second cap before first token.
        assert "upstream_status=503" in caplog.text
        assert "private-provider-key" not in caplog.text
        assert "private-upstream-prompt-and-key" not in caplog.text
    finally:
        server.shutdown(); server.server_close()


@pytest.mark.skipif(sys.platform == "win32", reason="Official native SDK is verified on Linux")
def test_official_native_sdk_reads_searches_and_runs_shell(tmp_path):
    init_db()
    source = tmp_path / "source"
    source.mkdir()
    (source / "provider.rs").write_text("fn device() { /* CUDA CoreML CPU */ }\n", encoding="utf-8")
    requests = []
    actions = [
        ("read", {"file_path": str(source / "provider.rs")}),
        ("bash", {"command": "printf native-shell-ok"}),
        ("write", {"file_path": str(tmp_path / "analysis.txt"), "content": "local-only"}),
        ("grep", {"pattern": "CUDA", "path": str(source)}),
    ]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(body)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            events = [("message_start", {"type": "message_start", "message": {"id": "test", "type": "message", "role": "assistant", "model": "test", "content": [], "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 0}}})]
            if len(requests) <= len(actions):
                name, args = actions[len(requests) - 1]
                events += [("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "tool_use", "id": "tool-" + str(len(requests)), "name": name, "input": {}}}),
                           ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": json.dumps(args)}})]
                reason = "tool_use"
            else:
                events += [("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
                           ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "原生能力验证完成"}})]
                reason = "end_turn"
            events += [("content_block_stop", {"type": "content_block_stop", "index": 0}),
                       ("message_delta", {"type": "message_delta", "delta": {"stop_reason": reason, "stop_sequence": None}, "usage": {"output_tokens": 10}}),
                       ("message_stop", {"type": "message_stop"})]
            for name, value in events:
                self.wfile.write(("event: " + name + "\ndata: " + json.dumps(value) + "\n\n").encode())
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        payload = dict(system=dsh.SYSTEM_PROMPT, model="test", gateway_url=f"http://127.0.0.1:{server.server_port}",
                       gateway_token="test", reasoning_effort="none", max_tokens=2048, prompt="{}", timeout=30)
        assert native_runtime.run(payload, tmp_path) == "原生能力验证完成"
        advertised = {t["name"] for t in requests[0]["tools"]}
        assert {"read", "write", "edit", "glob", "grep", "bash", "working_directory"} <= advertised
        assert advertised <= native_runtime.NATIVE_TOOLS
        assert (tmp_path / "analysis.txt").read_text() == "local-only"
        history = json.dumps(requests[-1], ensure_ascii=False)
        assert "native-shell-ok" in history and "CUDA CoreML CPU" in history
        assert "session_log" not in json.dumps(requests[0]).lower()
    finally:
        server.shutdown(); server.server_close()


def test_gateway_records_only_allowed_tool_metadata_and_observed_results(indexed, monkeypatch):
    from uuid import uuid4
    from requirement_platform import model_gateway
    from requirement_platform.collaboration_models import ModelRequestUsage
    from requirement_platform.conversation_usage import track_conversation

    cid, mid = str(uuid4()), str(uuid4())
    monkeypatch.setattr(model_gateway, "reserve_model", lambda *_: None)
    calls = [{"type": "tool_use", "id": f"private-id-{i}", "name": name, "input": {"secret": "private-arg"}}
             for i, name in enumerate(("read", "grep", "read", "not-allowed"))]

    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *_): pass

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            if not request["messages"]:
                for block in calls:
                    event = {"type": "content_block_start", "content_block": block}
                    self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())

    server = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    target = SimpleNamespace(model_name="test", api_base=f"http://127.0.0.1:{server.server_port}", api_key="test", timeout_seconds=5)
    results = [{"type": "tool_result", "tool_use_id": block["id"], "is_error": i == 1, "content": "private-result"}
               for i, block in enumerate(calls[:2])]
    history = [{"role": "assistant", "content": calls}, {"role": "user", "content": results}]
    try:
        with track_conversation("intake", cid, mid), model_gateway.bounded_endpoint(target, allowed_tools={"read", "grep"}, max_requests=3) as url:
            for messages in ([], history, history):
                assert httpx.post(url + "/v1/messages", json={"messages": messages}, trust_env=False).status_code == 200
        with model_gateway.SessionLocal() as db:
            usage = db.query(ModelRequestUsage).filter_by(conversation_id=cid, message_id=mid).order_by(ModelRequestUsage.created_at).all()
            trace = usage[0].tool_calls
            assert [(t["name"], t["status"]) for t in trace] == [("read", "completed"), ("grep", "failed"), ("read", "unconfirmed")]
            assert all(set(t) == {"name", "status", "created_at"} for t in trace)
            assert [t["created_at"] for t in trace] == sorted(t["created_at"] for t in trace)
            assert [r.tool_calls for r in usage[1:]] == [[], []]
    finally:
        server.shutdown(); server.server_close()
