# Codex CLI Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `fabulita bridge` exposes `codex exec` as a local OpenAI-compatible endpoint; the landing page gets a one-click "Codex CLI" provider preset.

**Architecture:** New stdlib-only `fabulita/bridge.py` (ThreadingHTTPServer, 127.0.0.1:8130, CORS, subprocess to `codex exec` with stdin prompt + `--output-last-message`), wired as a CLI subcommand. `docs/index.html` gains a `codex` entry in `PROV` + dropdown + i18n; generation pipeline unchanged.

**Tech Stack:** Python 3 stdlib (http.server, subprocess, tempfile, json, argparse), pytest (dev extra), vanilla ES5 JS.

**Spec:** `docs/superpowers/specs/2026-07-16-codex-bridge-design.md`

## Global Constraints

- `fabulita` package stays stdlib-only (no new runtime dependencies).
- Bridge binds 127.0.0.1 only; default port 8130.
- codex invocation exactly: `codex exec --ephemeral --skip-git-repo-check -s read-only --color never --output-last-message <tmp>/last.txt -C <tmp> [-m <model>] -` with prompt on stdin; 600 s subprocess timeout. (Flags verified against codex-cli 0.144.3.)
- Page changes follow the file's ES5 style (`var`, `function`, no arrows/template literals, double quotes); all four locales (zh ~line 181, en ~240, es ~299, ja ~358) get `provCodex`.
- Error bodies are OpenAI-style `{"error":{"message":"..."}}` — the page's `httpError` reads `error.message`.
- Python tests run via `uv run --extra dev pytest -q` from the repo root; browser QA is agent-driven per user directive.

---

### Task 1: `fabulita/bridge.py` + CLI wiring (TDD)

**Files:**
- Create: `fabulita/bridge.py`
- Modify: `fabulita/cli.py` (add `bridge` subparser; follow the existing `sub.add_parser` pattern around `fabulita/cli.py:25-68`)
- Test: `tests/test_bridge.py`

**Interfaces:**
- Produces: `bridge.build_cmd(model, out_path, workdir) -> list[str]`; `bridge.run_codex(prompt, model, timeout=600) -> str`; `bridge.make_server(port, default_model) -> ThreadingHTTPServer`; `bridge.main(args)` CLI entry with `--port` (default 8130) and `--model` (default None). CLI: `fabulita bridge [--port N] [--model M]`.

- [ ] **Step 1: Write the failing tests**

`tests/test_bridge.py`:

```python
import json
import os
import stat
import sys
import threading
import urllib.request
import urllib.error

import pytest

from fabulita import bridge


def test_build_cmd_without_model(tmp_path):
    cmd = bridge.build_cmd(None, str(tmp_path / "last.txt"), str(tmp_path))
    assert cmd[0:2] == ["codex", "exec"]
    assert "--ephemeral" in cmd and "--skip-git-repo-check" in cmd
    assert ["-s", "read-only"] == cmd[cmd.index("-s"):cmd.index("-s") + 2]
    assert "--output-last-message" in cmd
    assert cmd[-1] == "-"
    assert "-m" not in cmd


def test_build_cmd_with_model(tmp_path):
    cmd = bridge.build_cmd("gpt-5.3-codex", str(tmp_path / "last.txt"), str(tmp_path))
    assert cmd[cmd.index("-m") + 1] == "gpt-5.3-codex"


FAKE_OK = """#!/bin/sh
# fake codex: echo stdin into the --output-last-message file, prefixed
out=""
prev=""
for a in "$@"; do
  if [ "$prev" = "--output-last-message" ]; then out="$a"; fi
  prev="$a"
done
prompt=$(cat)
printf '{"answer":"echo:%s"}' "$prompt" > "$out"
"""

FAKE_FAIL = """#!/bin/sh
echo "boom: quota exceeded" >&2
exit 1
"""


def _fake_codex(tmp_path, script, monkeypatch):
    d = tmp_path / "bin"
    d.mkdir(exist_ok=True)
    p = d / "codex"
    p.write_text(script)
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", str(d) + os.pathsep + os.environ["PATH"])


@pytest.fixture
def server(tmp_path):
    srv = bridge.make_server(0, None)  # port 0 = ephemeral
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv
    srv.shutdown()


def _post(srv, body):
    req = urllib.request.Request(
        "http://127.0.0.1:%d/v1/chat/completions" % srv.server_address[1],
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    return urllib.request.urlopen(req)


def test_chat_completion_roundtrip(tmp_path, monkeypatch, server):
    _fake_codex(tmp_path, FAKE_OK, monkeypatch)
    res = _post(server, {"model": "", "messages": [{"role": "user", "content": "hola"}]})
    assert res.status == 200
    assert res.headers["Access-Control-Allow-Origin"] == "*"
    data = json.loads(res.read())
    assert data["choices"][0]["message"]["content"] == '{"answer":"echo:hola"}'
    assert data["choices"][0]["message"]["role"] == "assistant"


def test_codex_failure_returns_openai_error(tmp_path, monkeypatch, server):
    _fake_codex(tmp_path, FAKE_FAIL, monkeypatch)
    with pytest.raises(urllib.error.HTTPError) as ei:
        _post(server, {"messages": [{"role": "user", "content": "x"}]})
    assert ei.value.code == 500
    err = json.loads(ei.value.read())
    assert "boom" in err["error"]["message"]


def test_options_preflight(server):
    req = urllib.request.Request(
        "http://127.0.0.1:%d/v1/chat/completions" % server.server_address[1],
        method="OPTIONS",
    )
    res = urllib.request.urlopen(req)
    assert res.status == 204
    assert res.headers["Access-Control-Allow-Origin"] == "*"
    assert "POST" in res.headers["Access-Control-Allow-Methods"]


def test_bad_request_body(server):
    with pytest.raises(urllib.error.HTTPError) as ei:
        req = urllib.request.Request(
            "http://127.0.0.1:%d/v1/chat/completions" % server.server_address[1],
            data=b"not json", headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req)
    assert ei.value.code == 400


def test_unknown_path_404(server):
    with pytest.raises(urllib.error.HTTPError) as ei:
        urllib.request.urlopen("http://127.0.0.1:%d/nope" % server.server_address[1])
    assert ei.value.code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_bridge.py -q`
Expected: FAIL with `ModuleNotFoundError`/`AttributeError` (no `fabulita.bridge`).

- [ ] **Step 3: Implement `fabulita/bridge.py`**

```python
"""Local OpenAI-compatible bridge that runs prompts through `codex exec`.

The landing page / Studio speak OpenAI chat-completions to any base URL;
this server accepts those requests on 127.0.0.1 and shells out to the
Codex CLI, so a browser page can use a local CLI subscription as its
model provider.  Stdlib only.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CODEX_TIMEOUT = 600


def build_cmd(model, out_path, workdir):
    cmd = ["codex", "exec", "--ephemeral", "--skip-git-repo-check",
           "-s", "read-only", "--color", "never",
           "--output-last-message", out_path, "-C", workdir]
    if model:
        cmd += ["-m", model]
    cmd.append("-")
    return cmd


def run_codex(prompt, model, timeout=CODEX_TIMEOUT):
    with tempfile.TemporaryDirectory(prefix="fabulita-bridge-") as td:
        out_path = os.path.join(td, "last.txt")
        try:
            proc = subprocess.run(build_cmd(model, out_path, td),
                                  input=prompt.encode("utf-8"),
                                  capture_output=True, timeout=timeout)
        except FileNotFoundError:
            raise RuntimeError("codex CLI not found on PATH — install Codex CLI or adjust PATH")
        except subprocess.TimeoutExpired:
            raise RuntimeError("codex exec timed out after %d s" % timeout)
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or b"").decode("utf-8", "replace")[-2000:]
            raise RuntimeError(tail.strip() or "codex exec exited %d" % proc.returncode)
        try:
            with open(out_path, encoding="utf-8") as f:
                return f.read()
        except OSError:
            raise RuntimeError("codex exec produced no output message")


class _Handler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "content-type, authorization")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self):
        t0 = time.time()
        if self.path.rstrip("/") != "/v1/chat/completions":
            self._send(404, {"error": {"message": "unknown path %s" % self.path}})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length))
            parts = [m.get("content") for m in body.get("messages", [])
                     if isinstance(m.get("content"), str) and m.get("content")]
            if not parts:
                raise ValueError("no message content")
            prompt = "\n\n".join(parts)
            model = body.get("model") or self.server.default_model
        except (ValueError, KeyError, TypeError) as e:
            self._send(400, {"error": {"message": "bad request: %s" % e}})
            return
        try:
            text = run_codex(prompt, model)
        except RuntimeError as e:
            self._send(500, {"error": {"message": str(e)}})
            self._log(500, t0)
            return
        self._send(200, {
            "id": "fabulita-bridge", "object": "chat.completion",
            "model": model or "codex-default",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": text}}],
        })
        self._log(200, t0)

    def _log(self, status, t0):
        print("[bridge] %s %d %.1fs" % (self.path, status, time.time() - t0), flush=True)

    def log_message(self, *args):  # silence default per-request stderr noise
        pass


def make_server(port, default_model):
    srv = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    srv.default_model = default_model
    return srv


def main(args):
    srv = make_server(args.port, args.model)
    print("fabulita bridge: http://127.0.0.1:%d/v1  ->  codex exec%s"
          % (srv.server_address[1], " -m " + args.model if args.model else ""), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
```

- [ ] **Step 4: Wire the subcommand in `fabulita/cli.py`**

Following the existing pattern (see `fabulita/cli.py:25-68`), add after the `unpack` parser:

```python
    p = sub.add_parser("bridge", help="local OpenAI-compatible server backed by the Codex CLI (codex exec)")
    p.add_argument("--port", type=int, default=8130)
    p.add_argument("--model", default=None, help="codex model (-m); default: codex config default")
```

and in the dispatch section: the file dispatches with early `if args.cmd == "..."` blocks inside a `try:` (project-less commands like `studio` come first, before `proj.require()` — see `fabulita/cli.py:74-77`). Add the bridge block right before the `studio` block, at the same indentation:

```python
        if args.cmd == "bridge":
            from . import bridge
            return bridge.main(args)
```

(Lazy import keeps `bridge` free for other commands; `bridge` needs no project.)

- [ ] **Step 5: Run the tests**

Run: `uv run --extra dev pytest tests/test_bridge.py -q` → all pass.
Run: `uv run --extra dev pytest -q` → whole suite green.
Also: `uv run fabulita bridge --help` prints usage; `uv run python -c "from fabulita import bridge; print(bridge.build_cmd('m','/tmp/x','/tmp')[-1])"` prints `-`.

- [ ] **Step 6: Commit**

```bash
git add fabulita/bridge.py fabulita/cli.py tests/test_bridge.py
git commit -m "fabulita bridge: OpenAI-compatible local server backed by codex exec"
```

---

### Task 2: "Codex CLI" provider preset in the landing page

**Files:**
- Modify: `docs/index.html` (PROV ~line 424; genReady ~line 470; provLabel names ~line 489; settingsHtml select ~line 845 and key-field condition ~line 852; i18n zh/en/es/ja `provOllama` lines 181/240/299/358)

**Interfaces:**
- Consumes: existing `PROV`, `genReady`, `provLabel`, `settingsHtml`, i18n `L`.
- Produces: provider id `"codex"` usable end-to-end (stories + vocab parse).

- [ ] **Step 1: PROV entry**

In the `PROV` table add after `ollama`:

```js
  codex:     { base: "http://localhost:8130/v1", model: "", needKey: false },
```

- [ ] **Step 2: genReady + key field + names**

`genReady()`: change the ollama line to

```js
  if (g.provider === "ollama" || g.provider === "codex") return true;
```

`settingsHtml()` API-key condition: change `if (d.provider !== "ollama") {` to

```js
  if (d.provider !== "ollama" && d.provider !== "codex") {
```

`provLabel()` names map: add `codex: t("provCodex"),` after the `ollama` entry.

- [ ] **Step 3: dropdown option**

In `settingsHtml()` the provider `<select>` array (~line 845), insert `["codex", t("provCodex")]` right after the ollama pair:

```js
  [["ollama", t("provOllama")], ["codex", t("provCodex")], ["qwen", t("provQwen")], ["anthropic", t("provClaude")], ["custom", t("provCustom")]].forEach(function (c) {
```

- [ ] **Step 4: i18n (all four locales, next to `provOllama`)**

```js
    provCodex: "Codex CLI（本地桥 · fabulita bridge）",          // zh
    provCodex: "Codex CLI (local bridge · fabulita bridge)",     // en
    provCodex: "Codex CLI (puente local · fabulita bridge)",     // es
    provCodex: "Codex CLI（ローカルブリッジ · fabulita bridge）", // ja
```

- [ ] **Step 5: Verify**

1. `python3 -c "import re; h=open('docs/index.html').read(); m=re.findall(r'<script>(.*?)</script>', h, re.S); open('/tmp/fab-codex.js','w').write(m[-1])" && node --check /tmp/fab-codex.js` — clean.
2. `grep -c "provCodex" docs/index.html` — expect 6 (4 locale defs + names map + dropdown).
3. `grep -n "codex" docs/index.html | head` — PROV entry, genReady, key condition present.

- [ ] **Step 6: Commit**

```bash
git add docs/index.html
git commit -m "Landing page: Codex CLI provider preset (local fabulita bridge)"
```

---

### Task 3: Agent-driven browser QA (real codex, once)

**Files:** none (QA; fixes only if found)

**Interfaces:** consumes the running page (http://localhost:8901, server assumed up) and `uv run fabulita bridge` started for the test.

- [ ] **Step 1: Start the bridge** (controller: `uv run fabulita bridge` in background; confirm banner line).
- [ ] **Step 2: Smoke the bridge from shell** — `curl -s http://127.0.0.1:8130/v1/chat/completions -H 'content-type: application/json' -d '{"messages":[{"role":"user","content":"Reply with exactly the word: pong"}]}'` → JSON with a `choices[0].message.content` containing "pong" (this runs one real codex exec).
- [ ] **Step 3: Dispatch a browser-QA subagent** (user directive: browser testing runs via agent) with these ACCEPTANCE CRITERIA (set by the user 2026-07-16):
  1. **Middle-schooler usability**: walk the whole flow as a naive first-time user — word list in, story out, browser only, no console tricks. Every step must be discoverable from what is on screen (buttons/labels/hints). Log every point of friction or confusion (e.g. where is PDF upload, what to click after parsing, what ⚙ means) — friction points are findings even if the flow technically works.
  2. **Fresh-word batches**: after accepting a story, the next batch (chips shown before generating) must contain only words NOT used by any existing story (`vocab_used`); verify by comparing the visible chips against the accepted story's words, and cross-check `coverage` in localStorage. Report any overlap.
  3. Codex provider e2e: switch ⚙ provider to "Codex CLI（本地桥）", save, generate ONE story on 我的西语故事书, verify preview (sentences + glosses per project gloss_lang), accept it, coverage advances.
  4. Restore UI language to 中文 if changed; report everything found.
- [ ] **Step 4: Fix anything found, commit**

```bash
git add -A && git commit -m "QA fixes: codex bridge round 1"
```

(Skip if nothing found.)
