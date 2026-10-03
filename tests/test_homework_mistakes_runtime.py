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
    window.__homeworkMistakesRuntimeTest = {
      state,
      homeworkAssignments,
      homeworkItems,
      homeworkProgress,
      openHomework,
      saveHomeworkAnswer,
      checkHomeworkAnswer,
      homeworkMistakeEntries,
      resolveHomeworkMistake,
      homeworkMistakesHtml,
      dashboardReviewHtml
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
    crypto: { randomUUID: () => "homework-mistakes-runtime-uuid" },
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
  assert(context.__homeworkMistakesRuntimeTest,
    "runtime mistakes API was not exposed");
  return {
    runtime: context.__homeworkMistakesRuntimeTest,
    localStorage
  };
}

const page = bootPage(process.argv[1]);
const runtime = page.runtime;
const assignment = runtime.homeworkAssignments.find(
  (candidate) => candidate.id === "ser-estar-practice-a1-01"
);
assert(assignment, "expected the bilingual ser/estar assignment");

assert(runtime.homeworkMistakeEntries().length === 0,
  "a fresh profile should have no mistakes");
assert(runtime.homeworkMistakesHtml().indexOf("还没有错题") !== -1,
  "the empty state should render");

runtime.openHomework(assignment);
runtime.state.homeworkIndex = 0;               // correct answer "está"
runtime.saveHomeworkAnswer("es");
runtime.checkHomeworkAnswer();                  // wrong on first attempt
runtime.saveHomeworkAnswer("está");
runtime.checkHomeworkAnswer();                  // corrected in the assignment

const entries = runtime.homeworkMistakeEntries();
assert(entries.length === 1, "the first-attempt mistake should be collected");
assert(entries[0].resolved === false, "the mistake starts unresolved");
const key = entries[0].key;

const listHtml = runtime.homeworkMistakesHtml();
assert(listHtml.indexOf("错题") !== -1 && listHtml.indexOf("data-mistake-open") !== -1,
  "the mistake block should render an openable entry");
assert(runtime.dashboardReviewHtml().indexOf("错题") !== -1,
  "the review column should include the mistake block");

assert(runtime.resolveHomeworkMistake(key, "es") === "incorrect",
  "a wrong redo should not resolve the mistake");
assert(runtime.homeworkMistakeEntries()[0].resolved === false,
  "an incorrect redo keeps the entry unresolved");

assert(runtime.resolveHomeworkMistake(key, "está") === "correct",
  "the correct redo should be graded");
const after = runtime.homeworkMistakeEntries();
assert(after.length === 1 && after[0].resolved === true,
  "the entry should be marked resolved");
const progress = runtime.homeworkProgress(assignment);
const itemId = runtime.homeworkItems(assignment)[0].item.id;
assert(progress.responses[itemId].firstStatus === "incorrect" &&
    progress.responses[itemId].status === "correct" &&
    progress.responses[itemId].mistakeResolvedAt > 0,
  "resolving must only stamp mistakeResolvedAt");
"""


def test_homework_mistakes_runtime(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the inline homework mistakes test")

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
        "Node homework mistakes regression failed\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
