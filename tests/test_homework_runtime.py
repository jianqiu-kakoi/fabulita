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
    window.__homeworkRuntimeTest = {
      VOCAB_DASHBOARD,
      state,
      homeworkAssignments,
      homeworkScopeKey,
      homeworkById,
      homeworkItems,
      homeworkActiveItems,
      openHomework,
      saveHomeworkAnswer,
      checkHomeworkAnswer,
      homeworkProgress,
      homeworkStats,
      homeworkVerdict,
      retryHomeworkAnswers,
      reportHomeworkIssue,
      deleteHomeworkProgress,
      qaQuestions,
      dashboardHomeworkQuestionHtml
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
    crypto: { randomUUID: () => "homework-runtime-uuid" },
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
  assert(context.__homeworkRuntimeTest, "runtime test API was not exposed");
  return {
    P,
    runtime: context.__homeworkRuntimeTest,
    localStorage,
    app
  };
}

const page = bootPage(process.argv[1]);
const runtime = page.runtime;
const localStorage = page.localStorage;
const HOMEWORK_LS = "fabulita.homework.v1";
const REVIEW_LS = "fabulita.review.v1";
const EVENTS_LS = "fabulita.review.events.v1";
const QA_LS = "fabulita.qa.v1";

assert(runtime.VOCAB_DASHBOARD === true, "Mi Español should use the vocabulary dashboard");
const assignment = runtime.homeworkAssignments.find(
  (candidate) => candidate.id === "ejercicios-vocabulario-a1-1"
);
assert(assignment, "expected the A1 vocabulary homework assignment");
const items = runtime.homeworkItems(assignment);
assert(items.length === 50, "expected 50 runtime homework items");
assert(page.P.config.homework_id === "mi-espanol", "missing configured homework_id");
assert(runtime.homeworkScopeKey === "book:mi-espanol:es",
  "homework scope must use homework_id and language");

runtime.openHomework(assignment);
assert(runtime.state.homeworkId === assignment.id, "opening should select the assignment");
assert(runtime.state.homeworkIndex === 0, "opening a new assignment should start at the first item");
assert(runtime.homeworkActiveItems(assignment)[0].item.id === "p1-01",
  "the first interactive item should be p1-01");
const firstQuestionHtml = runtime.dashboardHomeworkQuestionHtml(assignment);
assert(firstQuestionHtml.includes("El _______ es el primer día de la semana."),
  "the first question should be rendered");
assert(firstQuestionHtml.includes('value="lunes"'), "the first choice should include lunes");

let stats = runtime.homeworkStats(assignment, runtime.homeworkProgress(assignment));
assert(stats.checked === 0 && stats.correct === 0, "new homework should have no score");
assert(runtime.saveHomeworkAnswer("lunes").saved === true, "lunes draft should save");
let freshProgress = runtime.homeworkProgress(assignment);
assert(freshProgress.responses["p1-01"].answer === "lunes", "choice draft should persist");
assert(!freshProgress.responses["p1-01"].status, "saving a draft must not score it");
assert(runtime.checkHomeworkAnswer() === true, "lunes should be checkable");
stats = runtime.homeworkStats(assignment, runtime.homeworkProgress(assignment));
assert(stats.checked === 1 && stats.correct === 1,
  "checking lunes should increment checked and correct exactly once");
assert(runtime.checkHomeworkAnswer() === true, "rechecking should remain supported");
stats = runtime.homeworkStats(assignment, runtime.homeworkProgress(assignment));
assert(stats.checked === 1 && stats.correct === 1,
  "rechecking one response must not double-count homework stats");

const coffeeIndex = items.findIndex((entry) => entry.item.id === "p2-15");
assert(coffeeIndex >= 0, "expected the Coffee translation item");
runtime.state.homeworkIndex = coffeeIndex;
assert(runtime.saveHomeworkAnswer("cafe").saved === true, "coffee draft should save");
const firstDraftRead = runtime.homeworkProgress(assignment);
const secondDraftRead = runtime.homeworkProgress(assignment);
assert(firstDraftRead !== secondDraftRead, "progress reads should return fresh values");
assert(firstDraftRead.responses["p2-15"].answer === "cafe" &&
    secondDraftRead.responses["p2-15"].answer === "cafe",
  "a text draft should persist across fresh progress reads");
assert(runtime.checkHomeworkAnswer() === true, "cafe should be checkable");
freshProgress = runtime.homeworkProgress(assignment);
assert(freshProgress.responses["p2-15"].status === "near_miss",
  "cafe should be a near_miss because the accent is missing");
assert(runtime.homeworkVerdict(items[coffeeIndex].item, "café") === "correct",
  "café should be correct");

localStorage.setItem(REVIEW_LS, '{"sentinel":"review"}');
localStorage.setItem(EVENTS_LS, '{"sentinel":"events"}');
const reviewBeforeIssue = localStorage.getItem(REVIEW_LS);
const eventsBeforeIssue = localStorage.getItem(EVENTS_LS);
const homeworkBeforeIssue = localStorage.getItem(HOMEWORK_LS);
const scoreBeforeIssue = JSON.stringify(
  runtime.homeworkStats(assignment, runtime.homeworkProgress(assignment))
);

runtime.reportHomeworkIssue();
let questions = runtime.qaQuestions();
assert(questions.length === 1, "reporting should add one Q&A item");
const issue = questions[0];
assert(issue.source === "homework_answer_issue", "missing homework issue source");
assert(issue.homeworkId === assignment.id, "missing homework id on Q&A issue");
assert(issue.homeworkItemId === "p2-15", "missing homework item id on Q&A issue");
assert(issue.submittedAnswer === "cafe", "missing submitted homework answer");
assert(issue.expectedAnswer === "café", "missing expected homework answer");
assert(issue.homeworkVerdict === "near_miss", "missing homework verdict");
assert(localStorage.getItem(REVIEW_LS) === reviewBeforeIssue,
  "homework issue reporting must not alter review storage");
assert(localStorage.getItem(EVENTS_LS) === eventsBeforeIssue,
  "homework issue reporting must not alter review events");
assert(localStorage.getItem(HOMEWORK_LS) === homeworkBeforeIssue,
  "homework issue reporting must not alter homework progress");
assert(JSON.stringify(runtime.homeworkStats(
  assignment, runtime.homeworkProgress(assignment)
)) === scoreBeforeIssue, "homework issue reporting must not alter the score");

runtime.reportHomeworkIssue();
questions = runtime.qaQuestions();
assert(questions.length === 1, "the same homework issue should be idempotent");
const qaAfterIssue = localStorage.getItem(QA_LS);
assert(qaAfterIssue, "the homework issue should remain persisted in Q&A");

runtime.retryHomeworkAnswers(assignment);
freshProgress = runtime.homeworkProgress(assignment);
assert(freshProgress.responses["p1-01"].status === "correct",
  "retry must preserve correct response status");
assert(freshProgress.responses["p1-01"].answer === "lunes",
  "retry must preserve correct response answers");
assert(freshProgress.responses["p2-15"].answer === "cafe",
  "retry should preserve the non-correct draft for editing");
assert(!freshProgress.responses["p2-15"].status,
  "retry must clear status for non-correct responses");
stats = runtime.homeworkStats(assignment, freshProgress);
assert(stats.checked === 1 && stats.correct === 1 && stats.near === 0,
  "retry should leave only the previously correct item scored");

const homeworkRoot = JSON.parse(localStorage.getItem(HOMEWORK_LS));
const scopedAssignments = homeworkRoot.scopes[runtime.homeworkScopeKey].assignments;
scopedAssignments["unrelated-homework"] = {
  responses: { untouched: { answer: "keep me", status: "correct" } },
  updatedAt: 1
};
localStorage.setItem(HOMEWORK_LS, JSON.stringify(homeworkRoot));
const reviewBeforeReset = localStorage.getItem(REVIEW_LS);
const eventsBeforeReset = localStorage.getItem(EVENTS_LS);
const qaBeforeReset = localStorage.getItem(QA_LS);

assert(runtime.deleteHomeworkProgress(assignment) === true,
  "reset should delete the current homework progress");
const afterResetRoot = JSON.parse(localStorage.getItem(HOMEWORK_LS));
const afterResetAssignments =
  afterResetRoot.scopes[runtime.homeworkScopeKey].assignments;
assert(assignment.id in afterResetAssignments &&
    Object.keys(afterResetAssignments[assignment.id].responses).length === 0 &&
    afterResetAssignments[assignment.id].resetAt > 0,
  "reset should keep an empty tombstone so another device cannot restore old answers");
assert(afterResetAssignments["unrelated-homework"].responses.untouched.answer === "keep me",
  "reset must preserve unrelated homework records");
assert(localStorage.getItem(REVIEW_LS) === reviewBeforeReset,
  "reset must preserve review storage");
assert(localStorage.getItem(EVENTS_LS) === eventsBeforeReset,
  "reset must preserve review events");
assert(localStorage.getItem(QA_LS) === qaBeforeReset &&
    localStorage.getItem(QA_LS) === qaAfterIssue,
  "reset must preserve the previously reported Q&A issue");
stats = runtime.homeworkStats(assignment, runtime.homeworkProgress(assignment));
assert(stats.checked === 0 && stats.correct === 0 && stats.near === 0,
  "the selected homework should have no score after reset");

const reader = bootPage(process.argv[2]);
assert(reader.runtime.VOCAB_DASHBOARD === false, "ordinary reader must not be a dashboard");
assert(reader.runtime.homeworkAssignments.length === 0,
  "ordinary reader should carry no runtime homework assignments");
assert(!reader.app.innerHTML.includes('data-dashboard-nav="homework"'),
  "ordinary reader must not render the homework navigation item");
"""


def test_homework_runtime_state_and_storage_isolation(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the inline homework runtime test")

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
    reader, _ = build.build_reader(tmp_path / "reader.html")

    result = subprocess.run(
        [node, "-e", NODE_RUNTIME_TEST, str(page), str(reader)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        "Node homework runtime regression failed\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
