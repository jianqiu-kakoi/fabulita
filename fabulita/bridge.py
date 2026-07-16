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
from urllib.parse import urlsplit

CODEX_TIMEOUT = 600


def origin_allowed(origin):
    """No Origin (curl, same-origin) is fine; browsers must be on localhost."""
    if not origin:
        return True
    try:
        u = urlsplit(origin)
    except ValueError:
        return False
    return u.scheme in ("http", "https") and u.hostname in ("localhost", "127.0.0.1")


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
        origin = self.headers.get("Origin")
        self.send_header("Access-Control-Allow-Origin", origin if origin else "*")
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Headers", "content-type, authorization")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        self._send(404, {"error": {"message": "unknown path %s" % self.path}})

    def do_POST(self):
        t0 = time.time()
        if not origin_allowed(self.headers.get("Origin")):
            self._send(403, {"error": {"message": "origin not allowed"}})
            self._log(403, t0)
            return
        if self.path.rstrip("/") != "/v1/chat/completions":
            self._send(404, {"error": {"message": "unknown path %s" % self.path}})
            self._log(404, t0)
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
            if model is not None and (not isinstance(model, str) or "\x00" in model):
                raise ValueError("bad model value")
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            self._send(400, {"error": {"message": "bad request: %s" % e}})
            self._log(400, t0)
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
    try:
        srv = make_server(args.port, args.model)
    except OSError as e:
        print("fabulita bridge: cannot bind port %d (%s) — is another bridge running? try --port" % (args.port, e), flush=True)
        return 1
    print("fabulita bridge: http://127.0.0.1:%d/v1  ->  codex exec%s"
          % (srv.server_address[1], " -m " + args.model if args.model else ""), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
