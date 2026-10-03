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
    window.__homeworkFirstAttemptRuntimeTest = {
      state,
      homeworkAssignments,
      homeworkItems,
      homeworkProgress,
      homeworkStats,
      openHomework,
      saveHomeworkAnswer,
      checkHomeworkAnswer,
      retryHomeworkAnswers,
      dashboardHomeworkSummaryHtml
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
    crypto: { randomUUID: () => "homework-first-attempt-runtime-uuid" },
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
  assert(context.__homeworkFirstAttemptRuntimeTest,
    "runtime first-attempt API was not exposed");
  return {
    runtime: context.__homeworkFirstAttemptRuntimeTest,
    localStorage
  };
}

const page = bootPage(process.argv[1]);
const runtime = page.runtime;
const assignment = runtime.homeworkAssignments.find(
  (candidate) => candidate.id === "ser-estar-practice-a1-01"
);
assert(assignment, "expected the bilingual ser/estar assignment");

runtime.openHomework(assignment);

// Item 0 (correct answer "está"): answer wrong first, then correct.
runtime.state.homeworkIndex = 0;
runtime.saveHomeworkAnswer("es");
assert(runtime.checkHomeworkAnswer() === true, "wrong answer should still grade");
let progress = runtime.homeworkProgress(assignment);
const itemId = runtime.homeworkItems(assignment)[0].item.id;
assert(progress.responses[itemId].status === "incorrect",
  "the wrong first answer should grade incorrect");
assert(progress.responses[itemId].firstStatus === "incorrect",
  "the first verdict should be recorded");

runtime.saveHomeworkAnswer("está");
runtime.checkHomeworkAnswer();
progress = runtime.homeworkProgress(assignment);
assert(progress.responses[itemId].status === "correct",
  "the corrected answer should grade correct");
assert(progress.responses[itemId].firstStatus === "incorrect",
  "firstStatus must never be overwritten by later attempts");

// Item 1 (correct answer "es"): correct on the first try.
runtime.state.homeworkIndex = 1;
runtime.saveHomeworkAnswer("es");
runtime.checkHomeworkAnswer();
progress = runtime.homeworkProgress(assignment);
const stats = runtime.homeworkStats(assignment, progress);
assert(stats.correct === 2, "current-state correct should count both items");
assert(stats.firstCorrect === 1 && stats.firstIncorrect === 1,
  "first-attempt stats should keep the initial mistake");

const summary = runtime.dashboardHomeworkSummaryHtml(assignment);
assert(summary.indexOf("<strong>1</strong><span>正确</span>") !== -1,
  "the summary tile should count first-attempt correct answers");
assert(summary.indexOf("订正后已答对 2 题") !== -1,
  "the summary should mention the corrected total");

// Item 2 (correct answer "estamos"): wrong first attempt, left uncorrected
// so it still carries a non-correct status when retryHomeworkAnswers runs
// below — this is what actually exercises the delete-status path.
runtime.state.homeworkIndex = 2;
runtime.saveHomeworkAnswer("es");
runtime.checkHomeworkAnswer();
progress = runtime.homeworkProgress(assignment);
const retriedItemId = runtime.homeworkItems(assignment)[2].item.id;
assert(progress.responses[retriedItemId].status === "incorrect",
  "the uncorrected item should grade incorrect");
assert(progress.responses[retriedItemId].firstStatus === "incorrect",
  "the uncorrected item's first verdict should be recorded");

// retry flow must not erase firstStatus
runtime.retryHomeworkAnswers(assignment);
progress = runtime.homeworkProgress(assignment);
assert(progress.responses[itemId] === undefined ||
    progress.responses[itemId].firstStatus === "incorrect",
  "retry reset must keep the first verdict");
assert(progress.responses[retriedItemId].status === undefined,
  "retryHomeworkAnswers must clear status on an item it actually retries");
assert(progress.responses[retriedItemId].firstStatus === "incorrect",
  "retryHomeworkAnswers must keep firstStatus on an item it actually retries");
assert(progress.responses[retriedItemId].firstCheckedAt > 0,
  "retryHomeworkAnswers must keep firstCheckedAt on an item it actually retries");
"""


def test_homework_first_attempt_scoring_runtime(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the inline homework first-attempt test")

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
        "Node homework first-attempt regression failed\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
