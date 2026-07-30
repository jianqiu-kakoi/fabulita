import shutil
import subprocess
from pathlib import Path

import pytest

from fabulita import build, vocab
from fabulita.project import Project


REPO = Path(__file__).parent.parent


NODE_RUNTIME_TEST = r"""
const fs = require("fs");
const vm = require("vm");

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function bootPage(pagePath) {
  const html = fs.readFileSync(pagePath, "utf8");
  const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)]
    .map((match) => match[1]);
  assert(scripts.length >= 2, "expected payload and application scripts");

  const payloadMatch = scripts[0].match(/^var P = ([\s\S]*);$/);
  assert(payloadMatch, "could not extract the built payload");
  const P = JSON.parse(payloadMatch[1]);

  let application = scripts[scripts.length - 1];
  const close = application.lastIndexOf("})();");
  assert(close !== -1, "could not find application IIFE");
  application = application.slice(0, close) + `
    window.__chatWidgetRuntimeTest = {
      state,
      chatMessages,
      sendChatMessage,
      chatWidgetHtml
    };
  ` + application.slice(close);

  const storage = new Map();
  const localStorage = {
    getItem(key) {
      return storage.has(key) ? storage.get(key) : null;
    },
    setItem(key, value) {
      storage.set(key, String(value));
    },
    removeItem(key) {
      storage.delete(key);
    }
  };

  const noop = () => {};
  const classList = {
    add: noop,
    remove: noop,
    toggle: noop,
    contains: () => false
  };
  const app = { className: "", innerHTML: "" };
  const pop = {
    classList,
    style: { setProperty: noop },
    offsetWidth: 0,
    offsetHeight: 0
  };
  const document = {
    body: { classList, appendChild: noop },
    documentElement: { lang: "" },
    activeElement: null,
    title: "",
    addEventListener: noop,
    getElementById(id) {
      if (id === "app") return app;
      if (id === "pop") return pop;
      return null;
    },
    querySelector() {
      return null;
    },
    querySelectorAll() {
      return [];
    },
    createElement() {
      return { style: {}, click: noop, remove: noop };
    }
  };

  class AudioStub {
    constructor() {
      this.currentTime = 0;
      this.playbackRate = 1;
      this.src = "";
    }
    pause() {}
    play() {
      return Promise.resolve();
    }
    addEventListener() {}
  }

  const context = {
    P,
    console,
    localStorage,
    document,
    location: { hash: "", reload: noop },
    navigator: {},
    setTimeout,
    clearTimeout,
    Intl,
    Date,
    Math,
    JSON,
    Blob: class BlobStub {},
    URL: { createObjectURL: () => "", revokeObjectURL: noop },
    crypto: { randomUUID: () => "chat-widget-runtime-uuid" },
    addEventListener: noop,
    scrollY: 0,
    scrollX: 0,
    innerWidth: 1200,
    innerHeight: 800,
    speechSynthesis: { cancel: noop, getVoices: () => [] },
    Audio: AudioStub
  };
  context.window = context;

  vm.createContext(context);
  vm.runInContext(application, context);
  assert(context.__chatWidgetRuntimeTest,
    "runtime chat widget API was not exposed");
  return {
    runtime: context.__chatWidgetRuntimeTest,
    localStorage
  };
}

const page = bootPage(process.argv[1]);
const runtime = page.runtime;

assert(runtime.chatMessages().length === 0, "chat history should start empty");
assert(runtime.chatWidgetHtml().indexOf("data-chat-toggle") !== -1,
  "the floating chat button should render");

runtime.state.chatOpen = true;
runtime.state.chatDraft = "帮我把这份作业换成新版本";
assert(runtime.sendChatMessage(runtime.state.chatDraft) === true,
  "sending a message should succeed");

const messages = runtime.chatMessages();
assert(messages.length === 2, "a send should store the message and the reply");
assert(messages[0].role === "user" &&
    messages[0].text === "帮我把这份作业换成新版本",
  "the user message should be stored verbatim");
assert(messages[1].role === "assistant" && messages[1].text === "收到",
  "the auto reply should be 收到");
assert(messages[0].at > 0 && messages[0].id, "messages carry id and timestamp");
assert(runtime.state.chatDraft === "", "the draft should clear after sending");

const stored = JSON.parse(page.localStorage.getItem("fabulita.chat.v1"));
assert(stored && stored.version === 1 && stored.scopes,
  "the chat store should persist under fabulita.chat.v1");

const html = runtime.chatWidgetHtml();
assert(html.indexOf("帮我把这份作业换成新版本") !== -1 && html.indexOf("收到") !== -1,
  "the open panel should render the conversation");

assert(runtime.sendChatMessage("   ") === false,
  "blank messages should be rejected");
assert(runtime.chatMessages().length === 2, "blank sends must not store anything");
"""


def test_chat_widget_runtime(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the inline chat widget test")

    source = REPO / "examples" / "mi-espanol"
    project_root = tmp_path / "mi-espanol"
    shutil.copytree(source, project_root)
    project = Project(project_root)
    vocab.import_file(project, project_root / "vocab.csv")
    page, _, _, _ = build.build(
        project,
        out=tmp_path / "mi-espanol.html",
        include_candidates=False,
        home="index.html",
    )

    result = subprocess.run(
        [node, "-e", NODE_RUNTIME_TEST, str(page)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        "Node chat widget regression failed\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
