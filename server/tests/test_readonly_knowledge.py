import io
import json
import tarfile
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from requirement_platform import knowledge
from requirement_platform.collaboration_models import KnowledgeFile, KnowledgeSnapshot
from requirement_platform.db import SessionLocal
from requirement_platform.main import app


@pytest.fixture
def indexed(tmp_path, monkeypatch):
    monkeypatch.setattr(knowledge, "settings", replace(knowledge.settings, knowledge_dir=str(tmp_path)))
    with TestClient(app):
        with SessionLocal() as db:
            db.query(KnowledgeFile).delete(); db.query(KnowledgeSnapshot).delete()
            db.add(KnowledgeSnapshot(id=1, tag="v-test", revision="a" * 40, code_count=1, docs_count=1))
            db.commit()
        code=[dict(path="package/server/export.py",kind="code",content="def export_photo(): return 'photo'",url="https://github.com/LC044/TrailSnap/blob/"+"a"*40+"/package/server/export.py")]
        docs=[dict(path="/docs/guide/export.html",kind="docs",content="行影集照片导出",url="https://trailsnap.cn/docs/guide/export.html")]
        manifest=knowledge.publish_files("a"*40,code,docs)
        (tmp_path/"current.json").write_text(json.dumps(manifest),encoding="utf-8")
        yield
        with SessionLocal() as db:
            db.query(KnowledgeFile).delete(); db.query(KnowledgeSnapshot).delete(); db.commit()


def test_archive_never_extracts_paths_or_links():
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, data, link in [
            ("release/package/server/good.py", b"print('source only')", False),
            ("release/package/desktop/src-tauri/src/llama_runtime.rs", b"fn windows_asset() {}", False),
            ("release/scripts/build-windows-installer.ps1", b"Write-Host 'build'", False),
            ("release/package/ai/Dockerfile.cpu", b"FROM python", False),
            ("release/package/ai/config.json", b'{"public": true}', False),
            ("release/.github/workflows/build.yml", b"name: build", False),
            ("release/Makefile", b"all: build", False),
            ("release/scripts/custom.unknown", b"plain text", False),
            ("release/scripts/.env.json", b"secret", False),
            ("release/scripts/token-secret.ps1", b"secret", False),
            ("release/package/desktop/src/binary.rs", b"\x00binary", False),
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
    assert [r["path"] for r in rows] == ["package/server/good.py", "package/desktop/src-tauri/src/llama_runtime.rs",
                                          "scripts/build-windows-installer.ps1", "package/ai/Dockerfile.cpu", "package/ai/config.json",
                                          ".github/workflows/build.yml", "Makefile", "scripts/custom.unknown"]


def test_image_cache_requires_exact_latest_revision(tmp_path, monkeypatch):
    import gzip
    monkeypatch.setattr(knowledge, "__file__", str(tmp_path / "knowledge.py"))
    cache = tmp_path / "release-source.json.gz"
    assert knowledge.bundled_code("a" * 40) is None
    cache.write_bytes(gzip.compress(json.dumps({"revision": "a" * 40, "files": [{"path": "code.py"}]}).encode()))
    assert knowledge.bundled_code("b" * 40) is None
    assert knowledge.bundled_code("a" * 40) is None  # Old indexing policy is incompatible too.
    cache.write_bytes(gzip.compress(json.dumps({"revision": "a" * 40, "index_version": knowledge.INDEX_VERSION, "files": [{"path": "code.py"}]}).encode()))
    assert knowledge.bundled_code("a" * 40) == [{"path": "code.py"}]
    cache.write_bytes(b"corrupt")
    assert knowledge.bundled_code("a" * 40) is None


@pytest.mark.parametrize("url", ["http://trailsnap.cn/docs/a.html", "https://trailsnap.cn.evil/docs/a.html", "https://user@trailsnap.cn/docs/a.html", "https://trailsnap.cn:443/docs/a.html", "https://127.0.0.1/docs/a.html", "https://trailsnap.cn/docs/../secret", "https://trailsnap.cn/docs/a.html?url=http://localhost", "https://trailsnap.cn/api/a"])
def test_docs_reject_arbitrary_origins_and_routes(url):
    assert not knowledge.official_doc_url(url)


def test_refresh_failure_retains_complete_snapshot(indexed, monkeypatch):
    from requirement_platform.collaboration_models import AIQuota
    with SessionLocal() as db: db.query(AIQuota).filter_by(key="knowledge-refresh").delete(); db.commit()
    monkeypatch.setattr(knowledge, "resolve_latest", lambda: ("new", "b" * 40))
    monkeypatch.setattr(knowledge, "fetch_code", lambda revision: [{"path": "x.py", "kind": "code", "url": "x", "content": "new"}])
    monkeypatch.setattr(knowledge, "fetch_docs", lambda: ([], 1))
    with pytest.raises(ValueError): knowledge.refresh_knowledge()
    with SessionLocal() as db:
        assert db.get(KnowledgeSnapshot, 1).revision == "a" * 40
        assert knowledge.current_manifest()["revision"] == "a" * 40
        assert knowledge.status(db)["ready"]


@pytest.mark.parametrize("used,should_refresh", [(0, True), (1, False), (2, False)])
def test_index_upgrade_rebuilds_same_sha_without_stealing_lease_or_retry_delay(indexed, monkeypatch, used, should_refresh):
    from datetime import timedelta
    from requirement_platform.collaboration_models import AIQuota
    from requirement_platform.models import utcnow
    with SessionLocal() as db:
        db.query(AIQuota).filter_by(key="knowledge-refresh").delete()
        db.add(AIQuota(key="knowledge-refresh", used=used, expires_at=utcnow() + timedelta(hours=1)))
        db.commit()
    fetched = []
    monkeypatch.setattr(knowledge, "resolve_latest", lambda: ("v-test", "a" * 40))
    monkeypatch.setattr(knowledge, "bundled_code", lambda revision: None)
    def fetch(revision):
        fetched.append(revision)
        return [{"path": "package/desktop/runtime.rs", "kind": "code", "content": "fn runtime() {}", "url": "source"}]
    monkeypatch.setattr(knowledge, "fetch_code", fetch)
    monkeypatch.setattr(knowledge, "fetch_docs", lambda: ([{"path": "/docs/a", "kind": "docs", "content": "public docs", "url": "docs"}], 1))
    knowledge.refresh_knowledge()
    assert bool(fetched) is should_refresh
    with SessionLocal() as db:
        assert db.get(KnowledgeSnapshot, 1).index_version == (knowledge.INDEX_VERSION if should_refresh else 0)
        if should_refresh:
            manifest = knowledge.current_manifest()
            assert "source/package/desktop/runtime.rs" in manifest["files"]
            assert "source/package/server/export.py" not in manifest["files"]
            assert db.query(KnowledgeFile).count() == 0
    if should_refresh:
        knowledge.refresh_knowledge()
        assert len(fetched) == 1  # Current policy retains the normal six-hour refresh interval.
