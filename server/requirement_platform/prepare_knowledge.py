"""Prepare a bounded public release cache in CI; never execute downloaded code."""
import gzip
import json
from pathlib import Path

from .knowledge import INDEX_VERSION, fetch_code, resolve_latest


def main():
    # Network outages must not make an otherwise valid application image unusable.
    # The worker can perform the same download after startup.
    try:
        tag, revision = resolve_latest()
        files = fetch_code(revision, timeout=300)
        body = json.dumps({"revision": revision, "index_version": INDEX_VERSION, "files": files}, ensure_ascii=False).encode()
        if not files or len(body) > 64 * 1024 * 1024:
            raise ValueError("Invalid bundle")
        Path(__file__).with_name("release-source.json.gz").write_bytes(gzip.compress(body))
        print(f"Prepared public source cache: {tag}, {len(files)} text files")
    except Exception:
        print("Public source cache unavailable; worker will download after startup")


if __name__ == "__main__":
    main()
