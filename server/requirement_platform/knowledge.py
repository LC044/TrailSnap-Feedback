"""Fixed public sources, bounded downloads, immutable release code, no extraction/execution."""
import json
import gzip
import re
import tarfile
import time
import uuid
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from tempfile import SpooledTemporaryFile
from urllib.parse import urlsplit, urljoin, quote
from xml.etree import ElementTree

import httpx
from sqlalchemy.dialects.sqlite import insert

from .collaboration_models import AIQuota, KnowledgeSnapshot
from .db import SessionLocal
from .models import utcnow
from .config import settings

REPO = "LC044/TrailSnap"
ORIGIN = "https://trailsnap.cn"
INDEX_VERSION = 2


def download(url, limit, *, timeout=8, docs=False):
    # URLs are exclusively constructed below, never supplied by a chat/tool.
    deadline = time.monotonic() + 25
    with httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False) as client:
        for attempt in range(3):
            if docs and not official_doc_url(url):
                raise ValueError("Invalid document URL")
            with client.stream("GET", url, headers={"User-Agent": "TrailSnap-Feedback", "Accept-Encoding": "identity"}) as response:
                if docs and response.status_code in {301, 302, 307, 308}:
                    url = urljoin(url, response.headers.get("location", ""))
                    continue
                response.raise_for_status()
                result = bytearray()
                for chunk in response.iter_bytes():
                    result.extend(chunk)
                    if len(result) > limit or time.monotonic() > deadline:
                        raise ValueError("Download limit exceeded")
                return bytes(result)
    raise ValueError("Too many document redirects")


def resolve_latest():
    release = json.loads(download(f"https://api.github.com/repos/{REPO}/releases/latest", 65536))
    tag = release["tag_name"]
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", tag):
        raise ValueError("Invalid release")
    commit = json.loads(download(f"https://api.github.com/repos/{REPO}/commits/{quote(tag, safe='')}", 512000))
    sha = commit["sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Invalid revision")
    return tag, sha


def archive_files(stream, revision):
    """Read regular text entries only. Archive names never become local paths."""
    result, selected, expanded = [], 0, 0
    with tarfile.open(fileobj=stream, mode="r|gz") as archive:
        for count, entry in enumerate(archive):
            expanded += entry.size
            if count > 30000 or expanded > 512 * 1024 * 1024:
                raise ValueError("Archive limit exceeded")
            parts = PurePosixPath(entry.name).parts
            if entry.name.startswith("/") or "\\" in entry.name or ".." in parts or len(parts) < 2:
                continue
            path = PurePosixPath(*parts[1:])
            if not entry.isfile() or not 0 < entry.size <= 1024 * 1024:
                continue
            if any(p in {".git", "node_modules", "vendor", "dist", "data", "uploads"} or p.startswith(".env") for p in path.parts):
                continue
            if any(word in path.name.lower() for word in ("secret", "credential")) or path.suffix in {".pem", ".key", ".p12", ".db", ".sqlite", ".sqlite3"}:
                continue
            data = archive.extractfile(entry).read()
            if b"\x00" in data:
                continue
            try:
                content = data.decode("utf-8")
            except UnicodeDecodeError:
                continue
            selected += entry.size
            if selected > 48 * 1024 * 1024 or len(result) >= 10000:
                raise ValueError("Source cache limit exceeded")
            result.append(dict(path=str(path), kind="code", content=content,
                               url=f"https://github.com/{REPO}/blob/{revision}/{quote(str(path))}"))
    return result


def fetch_code(revision, *, timeout=3600):
    deadline = time.monotonic() + timeout
    with SpooledTemporaryFile(max_size=4 * 1024 * 1024) as stream:
        with httpx.Client(timeout=httpx.Timeout(30, connect=10), follow_redirects=False, trust_env=False) as client:
            with client.stream("GET", f"https://codeload.github.com/{REPO}/tar.gz/{revision}") as response:
                response.raise_for_status()
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 96 * 1024 * 1024 or time.monotonic() > deadline:
                        raise ValueError("Source download limit exceeded")
                    stream.write(chunk)
        stream.seek(0)
        return archive_files(stream, revision)


def bundled_code(revision):
    """Image-owned release cache; only use it for the freshly resolved latest SHA."""
    path = Path(__file__).with_name("release-source.json.gz")
    if not path.is_file():
        return None
    try:
        with gzip.open(path, "rb") as stream:
            body = stream.read(64 * 1024 * 1024 + 1)
        if len(body) > 64 * 1024 * 1024:
            return None
        bundle = json.loads(body)
        return bundle["files"] if bundle["revision"] == revision and bundle.get("index_version") == INDEX_VERSION else None
    except (OSError, ValueError, KeyError):
        return None


def official_doc_url(value):
    parts = urlsplit(value)
    return (parts.scheme == "https" and parts.netloc == "trailsnap.cn" and not parts.query and not parts.fragment
            and re.fullmatch(r"/docs/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+(?:\.html)?/?", parts.path) is not None)


class DocText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.main = 0
        self.all_text, self.main_text = [], []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "nav", "header", "footer"}:
            self.hidden += 1
        if tag == "main":
            self.main += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "nav", "header", "footer"}:
            self.hidden = max(0, self.hidden - 1)
        if tag == "main":
            self.main = max(0, self.main - 1)

    def handle_data(self, data):
        if not self.hidden and data.strip():
            self.all_text.append(data.strip())
            if self.main:
                self.main_text.append(data.strip())


def fetch_docs():
    xml = ElementTree.fromstring(download(ORIGIN + "/sitemap.xml", 256000))
    urls = list(dict.fromkeys(node.text for node in xml.iter() if node.tag.endswith("}loc") and node.text and official_doc_url(node.text)))[:80]
    deadline = time.monotonic() + 70

    def fetch(url):
        if time.monotonic() > deadline:
            return None
        try:
            parser = DocText()
            parser.feed(download(url, 512000, timeout=5, docs=True).decode("utf-8"))
            content = "\n".join(parser.main_text or parser.all_text)[:24000]
            return dict(path=urlsplit(url).path, kind="docs", url=url, content=content) if len(content) >= 40 else None
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = [row for row in pool.map(fetch, urls) if row]
    return rows, len(urls)


def refresh_knowledge():
    """Worker owns refresh; public requests never trigger downloads."""
    with SessionLocal() as db:
        now = utcnow()
        db.execute(insert(AIQuota).values(key="knowledge-refresh", used=0, expires_at=now).on_conflict_do_nothing())
        old = db.get(KnowledgeSnapshot, 1)
        outdated = bool(old and old.index_version != INDEX_VERSION)
        # Upgrade an idle successful snapshot immediately, but respect an active
        # refresh lease and the failure retry delay.
        eligible = (AIQuota.expires_at <= now)
        if outdated:
            eligible = eligible | (AIQuota.used == 0)
        claimed = db.query(AIQuota).filter(AIQuota.key == "knowledge-refresh", eligible).update(
            {"used": 1, "expires_at": now + timedelta(minutes=70)}, synchronize_session=False)
        db.commit()
        if not claimed:
            return
    success = False
    try:
        tag, revision = resolve_latest()
        with SessionLocal() as db:
            old = db.get(KnowledgeSnapshot, 1)
            previous = current_manifest()
            same_revision = bool(old and old.revision == revision and old.index_version == INDEX_VERSION
                                 and previous and previous.get("revision") == revision)
        code = None if same_revision else bundled_code(revision)
        if same_revision:
            code = []
            for key, row in previous["files"].items():
                if row["kind"] == "code":
                    code.append({**row, "content": (Path(settings.knowledge_dir) / previous["generation"] / key).read_text(encoding="utf-8")})
        elif code is None:
            code = fetch_code(revision)
        if not code:
            raise ValueError("Empty code snapshot")
        docs, expected = fetch_docs()
        if not docs:
            raise ValueError("Official documents unavailable")
        manifest = publish_files(revision, code, docs)
        with SessionLocal() as db:
            snapshot = db.get(KnowledgeSnapshot, 1) or KnowledgeSnapshot(id=1)
            snapshot.tag, snapshot.revision, snapshot.refreshed_at = tag, revision, utcnow()
            snapshot.index_version = INDEX_VERSION
            snapshot.code_count = len(code)
            snapshot.docs_count = len(docs)
            snapshot.warning = "部分官网文档暂不可用" if len(docs) < expected else None
            db.add(snapshot)
            db.commit()
        marker = Path(settings.knowledge_dir) / "current-next.json"
        marker.write_text(json.dumps(manifest), encoding="utf-8")
        marker.replace(Path(settings.knowledge_dir) / "current.json")
        # Retain recent immutable generations so admitted runs can finish.
        # Delete only our generated public-cache directories, never arbitrary paths.
        root = Path(settings.knowledge_dir).resolve()
        for entry in root.iterdir():
            if (re.fullmatch(r"[0-9a-f]{40}-[0-9a-f]{16}", entry.name) and entry.is_dir()
                    and not entry.is_symlink() and entry.name != manifest["generation"]
                    and time.time() - entry.stat().st_mtime > 86400):
                shutil.rmtree(entry)
        success = True
    finally:
        with SessionLocal() as db:
            db.query(AIQuota).filter_by(key="knowledge-refresh").update(
                {"used": 0 if success else 2, "expires_at": utcnow() + timedelta(hours=6) if success else utcnow() + timedelta(minutes=10)})
            db.commit()


def current_manifest():
    try:
        value = json.loads((Path(settings.knowledge_dir) / "current.json").read_text(encoding="utf-8"))
        return value if value.get("format") == INDEX_VERSION else None
    except (OSError, ValueError):
        return None


def publish_files(revision, code, docs):
    """Materialize public text, never tar extraction or a keyword/vector index."""
    generation = revision + "-" + uuid.uuid4().hex[:16]
    root = Path(settings.knowledge_dir) / generation
    root.mkdir(parents=True, mode=0o755)
    files = {}
    for row in code + docs:
        relative = "source/" + row["path"] if row["kind"] == "code" else "docs/" + row["path"].removeprefix("/docs/").strip("/") + ".md"
        path = PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts or "\\" in relative:
            raise ValueError("Invalid public path")
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(row["content"], encoding="utf-8")
        files[relative] = {"path": row["path"], "url": row["url"], "kind": row["kind"]}
    manifest = {"format": INDEX_VERSION, "generation": generation, "revision": revision, "files": files}
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


def status(db):
    row = db.get(KnowledgeSnapshot, 1)
    if not row:
        refresh = db.get(AIQuota, "knowledge-refresh")
        return {"ready": False, "message": "资料下载暂时失败，后台会自动重试" if refresh and refresh.used == 2 else "代码与文档正在准备，请稍后再试"}
    manifest = current_manifest()
    if not manifest or manifest["revision"] != row.revision:
        return {"ready": False, "tag": row.tag, "revision": row.revision, "message": "公开源码与文档正在准备"}
    stale = utcnow().replace(tzinfo=None) - row.refreshed_at.replace(tzinfo=None) > timedelta(hours=12)
    return {"ready": True, "tag": row.tag, "revision": row.revision, "refreshed_at": row.refreshed_at.isoformat(),
            "docs_count": row.docs_count, "code_count": row.code_count, "stale": stale, "warning": row.warning,
            "index_version": row.index_version, "generation": manifest["generation"]}


class ReadOnlyKnowledge:
    """Snapshot metadata and citations only. DSH searches real files itself."""
    def __init__(self):
        with SessionLocal() as db:
            self.snapshot = status(db)
        self.sources = {}
        self.generation = self.snapshot.get("generation")
        self._manifest = None

    def observe(self, messages):
        if not self.generation:
            return
        if self._manifest is None:
            manifest = Path(settings.knowledge_dir) / self.generation / "manifest.json"
            self._manifest = json.loads(manifest.read_text(encoding="utf-8"))["files"]
        calls = {}
        for message in messages:
            blocks = message.get("content", [])
            if not isinstance(blocks, list):
                continue
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    calls[block.get("id")] = block
                elif block.get("type") == "tool_result" and not block.get("is_error"):
                    call = calls.get(block.get("tool_use_id"), {})
                    args = call.get("input", {})
                    if call.get("name") == "read":
                        self.add_source(args.get("file_path", ""), args.get("offset", 1))
                    # Search/shell result paths are references returned by actual
                    # native tools, never generated by our own search algorithm.
                    text = json.dumps(block.get("content", ""), ensure_ascii=False)[:24000]
                    for path in re.findall(r"(?:source|docs)/[A-Za-z0-9_./@+%()\-]+", text):
                        self.add_source(path.rstrip(".:"), 1)

    def add_source(self, path, line=1):
        if not isinstance(path, str):
            return
        for prefix in ("source/", "docs/"):
            if prefix in path:
                key = prefix + path.split(prefix, 1)[1]
                row = self._manifest.get(key)
                if row and len(self.sources) < 30:
                    line = line if type(line) is int and line > 0 else 1
                    self.sources[(key, line)] = {**row, "line": line,
                        "url": row["url"] + (f"#L{line}" if row["kind"] == "code" else "")}
                break
