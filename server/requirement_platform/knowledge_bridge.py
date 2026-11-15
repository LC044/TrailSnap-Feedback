"""Per-run loopback bridge. Its token/config never enters the model context."""
import json
import secrets
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


@contextmanager
def knowledge_bridge(knowledge):
    from .chat_activity import emit, observer
    activity = observer.get()  # Context variables do not propagate into HTTP threads.
    token = secrets.token_urlsafe(32)
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            if not secrets.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token):
                self.send_error(403)
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 2000:
                    raise ValueError("Too large")
                args = json.loads(self.rfile.read(size))
                name = self.path.removeprefix("/")
                with lock:
                    emit(name, sink=activity)
                    try:
                        result = knowledge.execute(name, args)
                    except Exception:
                        emit(name, "failed", sink=activity)
                        raise
                    emit(name, "completed", sink=activity)
                body = json.dumps(result, ensure_ascii=False).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                self.send_error(400, "Readonly retrieval unavailable")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield {"endpoint": f"http://127.0.0.1:{server.server_port}", "token": token}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)
