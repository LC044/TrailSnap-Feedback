"""Isolated Docker supervisor; each SDK process has a fresh unprivileged UID."""
import json
import logging
import os
import re
import secrets
import signal
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

slot = threading.BoundedSemaphore(1)
logger = logging.getLogger(__name__)


def execute(payload):
    if sys.platform != "linux" or os.getuid() != 0:
        raise RuntimeError("Native runner requires its isolated Linux container")
    url = urlsplit(payload["gateway_url"])
    if url.scheme != "http" or url.hostname not in {"api", "worker", "mcp", "host.docker.internal"} or not url.port or url.path:
        raise ValueError("Invalid gateway")
    with tempfile.TemporaryDirectory(prefix="analysis-", dir="/tmp") as directory:
        root = Path(directory)
        uid = secrets.randbelow(40000) + 20000
        os.chown(root, uid, uid)
        # Only published public material is mounted in this container. No API
        # database, .env, uploads, SMTP/GitHub/model credentials or Docker socket.
        generation = payload.pop("generation", None)
        if generation:
            if not re.fullmatch(r"[0-9a-f]{40}-[0-9a-f]{16}", generation):
                raise ValueError("Invalid snapshot")
            public = Path("/knowledge") / generation
            if not (public / "manifest.json").is_file():
                raise ValueError("Snapshot unavailable")
            for name in ("source", "docs"):
                (root / name).symlink_to(public / name, target_is_directory=True)
        environment = {"PATH": "/app/.venv/bin:/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": directory,
                       "TMPDIR": directory, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"}
        process = subprocess.Popen([sys.executable, str(Path(__file__).with_name("native_runtime.py"))],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   cwd=directory, env=environment, start_new_session=True,
                                   user=uid, group=uid, extra_groups=[])
        try:
            output, _ = process.communicate(json.dumps(payload).encode() + b"\n", timeout=min(105, payload.get("timeout", 100) + 3))
            if len(output) > 128000:
                raise RuntimeError("Runner failed")
            value = json.loads(output)
            if process.returncode:
                code = value.get("error_type", "RuntimeError")
                logger.warning("ai_runtime_failed error_type=%s", code if code in {"RuntimeError", "TimeoutError", "TransportClosedError", "TransportTimeoutError", "ConnectionError"} else "RuntimeError")
                raise RuntimeError("Runner failed")
            if not isinstance(value.get("reply"), str):
                raise RuntimeError("Runner failed")
            return value
        finally:
            # Shell background jobs must not outlive their request or keep files,
            # gateway credentials or a previous user's conversation accessible.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            # A command can create its own process group. Reap all processes
            # with this request's disposable UID as well as the original group.
            for entry in Path("/proc").iterdir():
                if entry.name.isdigit():
                    try:
                        if entry.stat().st_uid == uid:
                            os.kill(int(entry.name), signal.SIGKILL)
                    except (ProcessLookupError, FileNotFoundError):
                        pass
            process.wait(timeout=3)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.path != "/health":
            self.send_error(404)
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status":"healthy"}')

    def do_POST(self):
        token = os.environ.get("RP_DSH_RUNNER_TOKEN", "")
        if not token or not secrets.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token):
            self.send_error(403)
            return
        if self.path != "/run" or not slot.acquire(blocking=False):
            self.send_error(503)
            return
        try:
            started = time.monotonic()
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 65536:
                raise ValueError("Payload too large")
            result = execute(json.loads(self.rfile.read(length)))
            body = json.dumps(result, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as error:
            logger.warning("ai_runner_failed error_type=%s elapsed_ms=%d", type(error).__name__, int((time.monotonic()-started)*1000))
            try:
                self.send_error(503, "Analysis temporarily unavailable")
            except (BrokenPipeError, ConnectionResetError):
                pass
        finally:
            slot.release()


if __name__ == "__main__":
    if sys.platform != "linux" or os.getuid() != 0 or not os.environ.get("RP_DSH_RUNNER_TOKEN"):
        raise RuntimeError("Start with the isolated Docker runner configuration")
    ThreadingHTTPServer(("0.0.0.0", 8013), Handler).serve_forever()
