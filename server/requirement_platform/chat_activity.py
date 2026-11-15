"""Public progress is a closed vocabulary, never model text or tool arguments."""
from contextvars import ContextVar

observer = ContextVar("chat_activity_observer", default=None)
LABELS = {
    "preparing": "正在准备资料",
    "analyzing": "正在分析问题",
    "retrying": "正在重新连接服务",
    "composing": "正在整理回答",
    "read_trailsnap_source": "查阅相关代码",
    "search_official_docs": "检索官网文档",
}


def emit(kind, status="running", sink=None):
    callback = sink if sink is not None else observer.get()
    if callback and kind in LABELS and status in {"running", "completed", "failed"}:
        callback({"kind": kind, "label": LABELS[kind], "status": status})
