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


def test_messages_as_string_returns_400(server):
    with pytest.raises(urllib.error.HTTPError) as ei:
        _post(server, {"messages": "not a list"})
    assert ei.value.code == 400


def test_model_with_nul_returns_400(server):
    with pytest.raises(urllib.error.HTTPError) as ei:
        _post(server, {"model": "x\x00y", "messages": [{"role": "user", "content": "hi"}]})
    assert ei.value.code == 400


def test_evil_origin_rejected(server):
    req = urllib.request.Request(
        "http://127.0.0.1:%d/v1/chat/completions" % server.server_address[1],
        data=json.dumps({"messages": [{"role": "user", "content": "x"}]}).encode(),
        headers={"Content-Type": "application/json", "Origin": "https://evil.example"},
    )
    with pytest.raises(urllib.error.HTTPError) as ei:
        urllib.request.urlopen(req)
    assert ei.value.code == 403


def test_localhost_origin_allowed_and_echoed(tmp_path, monkeypatch, server):
    _fake_codex(tmp_path, FAKE_OK, monkeypatch)
    req = urllib.request.Request(
        "http://127.0.0.1:%d/v1/chat/completions" % server.server_address[1],
        data=json.dumps({"messages": [{"role": "user", "content": "hi"}]}).encode(),
        headers={"Content-Type": "application/json", "Origin": "http://localhost:8901"},
    )
    res = urllib.request.urlopen(req)
    assert res.status == 200
    assert res.headers["Access-Control-Allow-Origin"] == "http://localhost:8901"
