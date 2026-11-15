import io
import json
import tarfile
import sys
import threading
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from uuid import uuid4
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest
from fastapi.testclient import TestClient

from requirement_platform import knowledge
from requirement_platform.collaboration_models import KnowledgeFile, KnowledgeSnapshot
from requirement_platform.db import SessionLocal
from requirement_platform.main import app
from requirement_platform.knowledge_bridge import knowledge_bridge
from test_z_collaboration import actor


@pytest.fixture
def indexed():
    with TestClient(app):
        with SessionLocal() as db:
            db.query(KnowledgeFile).delete(); db.query(KnowledgeSnapshot).delete()
            db.add(KnowledgeSnapshot(id=1, tag="v-test", revision="a" * 40, code_count=1, docs_count=1))
            db.add_all([
                KnowledgeFile(path="package/server/export.py", kind="code", content="def export_photo():\n    return 'photo'\n", url="https://github.com/LC044/TrailSnap/blob/" + "a" * 40 + "/package/server/export.py"),
                KnowledgeFile(path="/docs/guide/export.html", kind="docs", content="行影集照片导出\n打开照片后点击导出。", url="https://trailsnap.cn/docs/guide/export.html"),
            ])
            db.commit()
        yield
        with SessionLocal() as db:
            db.query(KnowledgeFile).delete(); db.query(KnowledgeSnapshot).delete(); db.commit()


def test_tools_scope_evidence_and_run_limits(indexed):
    reader = knowledge.ReadOnlyKnowledge()
    result = reader.execute("search_trailsnap_code", {"query": "export_photo"})
    assert result["results"][0]["path"] == "package/server/export.py"
    assert result["snapshot"]["revision"] == "a" * 40
    assert reader.execute("search_official_docs", {"query": "导出"})["results"][0]["url"].startswith(knowledge.ORIGIN)
    assert "def export_photo" in reader.execute("read_trailsnap_source", {"path": "package/server/export.py"})["text"]
    with pytest.raises(ValueError): reader.execute("read_trailsnap_source", {"path": "../../.env"})
    with pytest.raises(ValueError): reader.execute("bash", {"command": "pwd"})
    reader.execute("search_official_docs", {"query": "no_match"})
    with pytest.raises(ValueError): reader.execute("search_official_docs", {"query": "导出"})
    assert len(reader.sources) == 2


def test_archive_never_extracts_paths_or_links():
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, data, link in [
            ("release/package/server/good.py", b"print('source only')", False),
            ("release/../../escape.py", b"bad", False),
            ("release/package/server/.env.py", b"secret", False),
            ("release/package/server/linked.py", b"", True),
            ("release/package/server/credentials.py", b"secret", False),
        ]:
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            if link: entry.type = tarfile.SYMTYPE; entry.linkname = "/etc/passwd"
            archive.addfile(entry, io.BytesIO(data))
    buffer.seek(0)
    rows = knowledge.archive_files(buffer, "a" * 40)
    assert [r["path"] for r in rows] == ["package/server/good.py"]


def test_image_cache_requires_exact_latest_revision(tmp_path, monkeypatch):
    import gzip
    monkeypatch.setattr(knowledge, "__file__", str(tmp_path / "knowledge.py"))
    cache = tmp_path / "release-source.json.gz"
    assert knowledge.bundled_code("a" * 40) is None
    cache.write_bytes(gzip.compress(json.dumps({"revision": "a" * 40, "files": [{"path": "code.py"}]}).encode()))
    assert knowledge.bundled_code("b" * 40) is None
    assert knowledge.bundled_code("a" * 40) == [{"path": "code.py"}]
    cache.write_bytes(b"corrupt")
    assert knowledge.bundled_code("a" * 40) is None


@pytest.mark.parametrize("url", ["http://trailsnap.cn/docs/a.html", "https://trailsnap.cn.evil/docs/a.html", "https://user@trailsnap.cn/docs/a.html", "https://trailsnap.cn:443/docs/a.html", "https://127.0.0.1/docs/a.html", "https://trailsnap.cn/docs/../secret", "https://trailsnap.cn/docs/a.html?url=http://localhost", "https://trailsnap.cn/api/a"])
def test_docs_reject_arbitrary_origins_and_routes(url):
    assert not knowledge.official_doc_url(url)


def test_bridge_authentication_and_no_arbitrary_tools(indexed):
    with knowledge_bridge(knowledge.ReadOnlyKnowledge()) as bridge:
        request = Request(bridge["endpoint"] + "/search_official_docs", data=b'{"query":"export"}', headers={"Authorization": "Bearer wrong"})
        with pytest.raises(HTTPError) as denied: urlopen(request)
        assert denied.value.code == 403
        request = Request(bridge["endpoint"] + "/bash", data=b'{}', headers={"Authorization": "Bearer " + bridge["token"]})
        with pytest.raises(HTTPError) as denied: urlopen(request)
        assert denied.value.code == 400


def test_new_chat_uses_readonly_tools_and_consultation_never_creates_draft(indexed, monkeypatch):
    from requirement_platform.api import intake
    from requirement_platform.models import Requirement
    import secrets
    calls = []
    def run(target, prompt, **kwargs):
        reader = kwargs["knowledge"]
        calls.append(json.loads(prompt))
        reader.execute("search_official_docs", {"query": "导出"})
        return json.dumps({"reply": "打开照片后点击导出。", "draft": {"type": "feature", "title": "行影集照片导出", "description": "希望在行影集中改进照片导出的使用体验。"}}, ensure_ascii=False)
    monkeypatch.setattr(intake, "resolve_model_targets", lambda *args: [object()])
    monkeypatch.setattr(intake.dsh, "run_harness", run)
    with TestClient(app) as client:
        with SessionLocal() as db: before = db.query(Requirement).count()
        response = client.post("/api/intake/messages", headers={**actor(), "X-Intake-Key": secrets.token_urlsafe(32)}, json={"content": "行影集如何导出照片？", "mode": "consultation"})
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["draft"] is None
        assert data["sources"][0]["kind"] == "docs"
        assert data["snapshot"]["tag"] == "v-test"
        assert calls[0]["mode"] == "consultation"
        with SessionLocal() as db: assert db.query(Requirement).count() == before


def test_refresh_failure_retains_complete_snapshot(indexed, monkeypatch):
    from requirement_platform.collaboration_models import AIQuota
    with SessionLocal() as db: db.query(AIQuota).filter_by(key="knowledge-refresh").delete(); db.commit()
    monkeypatch.setattr(knowledge, "resolve_latest", lambda: ("new", "b" * 40))
    monkeypatch.setattr(knowledge, "fetch_code", lambda revision: [{"path": "x.py", "kind": "code", "url": "x", "content": "new"}])
    monkeypatch.setattr(knowledge, "fetch_docs", lambda: ([], 1))
    with pytest.raises(ValueError): knowledge.refresh_knowledge()
    with SessionLocal() as db:
        assert db.get(KnowledgeSnapshot, 1).revision == "a" * 40
        assert db.query(KnowledgeFile).count() == 2


@pytest.mark.skipif(sys.platform == 'win32', reason='Official native SDK runtime is verified on Linux')
def test_official_runtime_executes_only_scoped_plugin(indexed, monkeypatch, tmp_path):
    from requirement_platform import dsh
    requests, unavailable = [], []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path.startswith('/offline/'):
                unavailable.append(body)
                self.send_error(503)
                return
            requests.append(body)
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream'); self.end_headers()
            events = [('message_start', {'type': 'message_start', 'message': {'id': 'test', 'type': 'message', 'role': 'assistant', 'model': 'deepseek-chat', 'content': [], 'stop_reason': None, 'stop_sequence': None, 'usage': {'input_tokens': 10, 'output_tokens': 0}}})]
            if len(requests) == 1:
                events += [
                    ('content_block_start', {'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'tool_use', 'id': 'tool-1', 'name': 'search_official_docs', 'input': {}}}),
                    ('content_block_delta', {'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'input_json_delta', 'partial_json': '{"query":"导出"}'}}),
                ]
                stop = 'tool_use'
            else:
                events += [
                    ('content_block_start', {'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}}),
                    ('content_block_delta', {'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': '打开照片后点击导出。'}}),
                ]
                stop = 'end_turn'
            events += [('content_block_stop', {'type': 'content_block_stop', 'index': 0}),
                       ('message_delta', {'type': 'message_delta', 'delta': {'stop_reason': stop, 'stop_sequence': None}, 'usage': {'output_tokens': 10}}),
                       ('message_stop', {'type': 'message_stop'})]
            for name, event in events:
                self.wfile.write(('event: ' + name + '\ndata: ' + json.dumps(event) + '\n\n').encode())
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    monkeypatch.setattr(dsh, 'settings', replace(dsh.settings, dsh_home=str(tmp_path)))
    reader = knowledge.ReadOnlyKnowledge()
    target = SimpleNamespace(model_name='deepseek-chat', api_base=f'http://127.0.0.1:{server.server_port}/v1', api_key='test', timeout_seconds=15, reasoning_effort='none')
    try:
        offline = SimpleNamespace(**{**vars(target), 'api_base': f'http://127.0.0.1:{server.server_port}/offline/v1'})
        result = dsh.run_with_fallback([offline, target], '{}', knowledge=reader)
        assert result == '打开照片后点击导出。'
        assert len(requests) == 2
        assert len(unavailable) == 1  # No hidden SDK retries before fallback.
        assert {t['name'] for t in requests[0]['tools']} == knowledge.TOOLS
        assert 'tools' not in requests[1]
        assert 'tool_choice' not in requests[1]
        assert '打开照片后点击导出' in json.dumps(requests[1], ensure_ascii=False)
        assert reader.calls == 1
        assert len(reader.sources) == 1
        assert 'readonly-knowledge' not in result
    finally:
        server.shutdown(); server.server_close()
