"""Official SDK child process. No platform imports or production credentials."""
import json
import os
import threading
from pathlib import Path

NATIVE_TOOLS = frozenset({"read", "read_image", "write", "edit", "apply_patch", "glob", "grep", "bash", "pwsh", "working_directory"})
EFFORTS = {"none": "off", "minimal": "low", "low": "low", "medium": "low", "high": "high", "xhigh": "max", "max": "max"}
PATCH = """- id: session-log-deepseek
  disabled: true
- id: plugin-package-inventory-deepseek
  disabled: true
- id: llm-retry
  disabled: true
- id: tool-fs
  config:
    read: true
    readImage: true
    write: true
    edit: true
    applyPatch: true
    readLimit: 300
    readMaxBytes: 12000
- id: persistent-bash
  config:
    timeoutMs: 20000
- id: llm-deepseek
  config:
    apiKeyEnv: DEEPSEEK_API_KEY
    defaultContextWindow: 65536
    streamIdleTimeoutMs: 45000
- insert:
    - id: tool-fs-search
      name: '@deepseek-ai/dsh-tool-fs-search'
      config:
        sampleOverCapGlobResults: true
        grepMaxMatches: 40
        globMaxResults: 100
"""


def run(payload, workspace):
    from deepseek_harness import DeepSeekHarness
    home = Path(workspace) / "home"
    home.mkdir()
    patch = Path(workspace) / "native.yml"
    patch.write_text(PATCH, encoding="utf-8")
    environment = {k: "" for k in os.environ if k not in {"PATH", "LANG", "LC_ALL", "TZ", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT"}}
    environment.update(HOME=str(home), USERPROFILE=str(home), TMPDIR=str(workspace),
                       DSH_TELEMETRY_DISABLED="1", DSH_PRIMARY_RUNTIME="", DSH_SYSTEM_PROMPT=payload["system"])
    with DeepSeekHarness(profile="sdk-minimal", cwd=str(workspace), dsh_home=str(home / "dsh"),
                         patches=(str(patch),), model=payload["model"], api_key=payload["gateway_token"],
                         base_url=payload["gateway_url"], max_tokens=payload["max_tokens"],
                         reasoning_effort=EFFORTS[payload["reasoning_effort"]],
                         request_timeout_seconds=payload.get("request_timeout", 45), env=environment) as harness:
        expired = threading.Event()
        def expire():
            expired.set()
            harness.close()
        timer = threading.Timer(payload.get("timeout", 100), expire)
        timer.daemon = True
        timer.start()
        try:
            result = harness.run("请处理以下 JSON 资料：\n" + payload["prompt"])
        except Exception:
            if expired.is_set():
                raise TimeoutError("analysis_deadline") from None
            raise
        finally:
            timer.cancel()
    if expired.is_set():
        raise TimeoutError("analysis_deadline")
    if result.finish_reason in {"error", "cancelled", "max_tokens", "max-tokens"} or not result.final_response.strip():
        raise RuntimeError("Analysis incomplete")
    return result.final_response.strip()


if __name__ == "__main__":
    import sys
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (32 * 1024 * 1024, 32 * 1024 * 1024))
        body = json.loads(sys.stdin.buffer.readline(65537))
        print(json.dumps({"reply": run(body, Path.cwd())}, ensure_ascii=False), flush=True)
    except Exception as error:
        # Class only: SDK exception text can contain prompts, paths or keys.
        print(json.dumps({"error_type": type(error).__name__}), flush=True)
        sys.exit(1)
