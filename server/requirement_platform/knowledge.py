"""Fixed public sources, bounded downloads, immutable release code, no extraction/execution."""
import json
import gzip
import re
import tarfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from tempfile import SpooledTemporaryFile
from urllib.parse import urlsplit, urljoin, quote
from xml.etree import ElementTree

import httpx
from sqlalchemy.dialects.sqlite import insert

from .collaboration_models import AIQuota, KnowledgeFile, KnowledgeSnapshot
from .db import SessionLocal
from .models import utcnow

REPO = "LC044/TrailSnap"
ORIGIN = "https://trailsnap.cn"
TOOLS = frozenset({"search_trailsnap_code", "read_trailsnap_source", "search_official_docs"})
TEXT_SUFFIXES = {".py", ".vue", ".ts", ".tsx", ".js", ".css", ".scss", ".md", ".toml", ".yaml", ".yml"}


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
            if not entry.isfile() or not 0 < entry.size <= 192000 or path.suffix not in TEXT_SUFFIXES:
                continue
            if any(p.startswith(".") or p in {"node_modules", "vendor", "dist", "data", "uploads"} for p in path.parts):
                continue
            if not (str(path).startswith(("package/", "doc/")) or str(path) in {"README.md", "CONTRIBUTING.md"}):
                continue
            if any(word in path.name.lower() for word in ("secret", "credential", "lock")):
                continue
            selected += entry.size
            if selected > 24 * 1024 * 1024 or len(result) >= 5000:
                raise ValueError("Source index limit exceeded")
            data = archive.extractfile(entry).read()
            if b"\x00" in data:
                continue
            try:
                content = data.decode("utf-8")
            except UnicodeDecodeError:
                continue
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
            body = stream.read(32 * 1024 * 1024 + 1)
        if len(body) > 32 * 1024 * 1024:
            return None
        bundle = json.loads(body)
        return bundle["files"] if bundle["revision"] == revision else None
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
        claimed = db.query(AIQuota).filter(AIQuota.key == "knowledge-refresh", AIQuota.expires_at <= now).update(
            {"used": 1, "expires_at": now + timedelta(minutes=70)}, synchronize_session=False)
        db.commit()
        if not claimed:
            return
    success = False
    try:
        tag, revision = resolve_latest()
        with SessionLocal() as db:
            old = db.get(KnowledgeSnapshot, 1)
            same_revision = bool(old and old.revision == revision)
        code = None if same_revision else bundled_code(revision)
        if code is None and not same_revision:
            code = fetch_code(revision)
        if code is not None and not code:
            raise ValueError("Empty code snapshot")
        docs, expected = fetch_docs()
        if not docs:
            raise ValueError("Official documents unavailable")
        with SessionLocal() as db:
            if code is not None:
                db.query(KnowledgeFile).filter_by(kind="code").delete()
                db.bulk_insert_mappings(KnowledgeFile, code)
            db.query(KnowledgeFile).filter_by(kind="docs").delete()
            db.bulk_insert_mappings(KnowledgeFile, docs)
            snapshot = db.get(KnowledgeSnapshot, 1) or KnowledgeSnapshot(id=1)
            snapshot.tag, snapshot.revision, snapshot.refreshed_at = tag, revision, utcnow()
            snapshot.code_count = db.query(KnowledgeFile).filter_by(kind="code").count()
            snapshot.docs_count = len(docs)
            snapshot.warning = "部分官网文档暂不可用" if len(docs) < expected else None
            db.add(snapshot)
            db.commit()
        success = True
    finally:
        with SessionLocal() as db:
            db.query(AIQuota).filter_by(key="knowledge-refresh").update(
                {"used": 0 if success else 2, "expires_at": utcnow() + timedelta(hours=6) if success else utcnow() + timedelta(minutes=10)})
            db.commit()


def status(db):
    row = db.get(KnowledgeSnapshot, 1)
    if not row:
        refresh = db.get(AIQuota, "knowledge-refresh")
        return {"ready": False, "message": "资料下载暂时失败，后台会自动重试" if refresh and refresh.used == 2 else "代码与文档正在准备，请稍后再试"}
    stale = utcnow().replace(tzinfo=None) - row.refreshed_at.replace(tzinfo=None) > timedelta(hours=12)
    return {"ready": True, "tag": row.tag, "revision": row.revision, "refreshed_at": row.refreshed_at.isoformat(),
            "docs_count": row.docs_count, "code_count": row.code_count, "stale": stale, "warning": row.warning}


class ReadOnlyKnowledge:
    """One run, one immutable revision, bounded literal searches and reads."""
    def __init__(self):
        with SessionLocal() as db:
            self.snapshot = status(db)
        # Load the large index only when the admitted model actually requests a
        # tool, inside the global model lease, not for every inbound HTTP request.
        self.files = None
        self.calls = 0
        self.sources = {}

    def excerpt(self, row, start, end):
        lines = row["content"].splitlines()
        text = "\n".join(f"{i + 1}: {line[:500]}" for i, line in enumerate(lines[start - 1:end], start - 1))[:5000]
        source = {"path": row["path"], "url": row["url"] + (f"#L{start}" if row["kind"] == "code" else ""),
                  "kind": row["kind"], "line": start}
        self.sources[(row["path"], start)] = source
        return {**source, "text": text}

    def execute(self, name, args):
        self.calls += 1
        if name not in TOOLS or self.calls > 6 or not isinstance(args, dict):
            raise ValueError("Retrieval limit exceeded")
        if not self.snapshot["ready"]:
            return {"unavailable": True, "message": self.snapshot["message"]}
        if self.files is None:
            with SessionLocal() as db:
                db.connection().exec_driver_sql("BEGIN")
                current = status(db)
                if current.get("revision") != self.snapshot.get("revision") or current.get("refreshed_at") != self.snapshot.get("refreshed_at"):
                    return {"unavailable": True, "message": "资料刚刚更新，请重新提问以使用最新快照"}
                self.files = {r.path: {"path": r.path, "kind": r.kind, "url": r.url, "content": r.content}
                              for r in db.query(KnowledgeFile)}
        if name == "read_trailsnap_source":
            if set(args) - {"path", "start_line"} or not isinstance(args.get("path"), str):
                raise ValueError("Invalid source path")
            row = self.files.get(args["path"])
            start = args.get("start_line", 1)
            if not row or row["kind"] != "code" or type(start) is not int or not 1 <= start <= 100000:
                raise ValueError("Source unavailable")
            return self.excerpt(row, start, start + 49)
        query = args.get("query")
        if set(args) != {"query"} or not isinstance(query, str) or not 1 <= len(query.strip()) <= 120:
            raise ValueError("Invalid search")
        # Literal terms only; never a shell command, regex, SQL fragment or URL.
        raw_terms = re.findall(r"[A-Za-z_][A-Za-z0-9_]{1,40}|[\u4e00-\u9fff]{2,20}", query.lower())
        terms = list(dict.fromkeys(raw_terms + [term[i:i + 2] for term in raw_terms if re.fullmatch(r"[\u4e00-\u9fff]+", term) for i in range(len(term) - 1)]))
        terms = [term for term in terms if term not in {"行影集", "如何", "怎么", "什么", "问题", "的使", "使用"}][:20]
        kind = "docs" if name == "search_official_docs" else "code"
        ranked = []
        for row in self.files.values():
            if row["kind"] != kind:
                continue
            content = row["content"].lower()
            score = sum((min(content.count(term), 8) + (10 if term in row["path"].lower() else 0)) * min(len(term), 8) for term in terms)
            if score:
                ranked.append((score, row))
        result = []
        for _, row in sorted(ranked, key=lambda pair: (-pair[0], pair[1]["path"]))[:3]:
            lines = row["content"].splitlines()
            hit = max(range(len(lines)), key=lambda i: sum(len(t) for t in terms if t in lines[i].lower()), default=0)
            result.append(self.excerpt(row, max(1, hit - 3), hit + 24))
        return {"snapshot": self.snapshot, "results": result}
