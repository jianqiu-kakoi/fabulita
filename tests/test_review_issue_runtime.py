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

const html = fs.readFileSync(process.argv[1], "utf8");
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
  window.__reviewRuntimeTest = {
    state,
    reportReviewIssue,
    qaQuestions,
    rateReview,
    reviewEvents,
    reviewAnswerMatches,
    reviewStore,
    vocabWords,
    reviewCardKey,
    normalizeReviewEvent,
    reviewHistorySummary,
    progressHistoryRowsHtml
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
  style: {},
  offsetWidth: 0,
  offsetHeight: 0
};
const document = {
  body: { classList, appendChild: noop },
  documentElement: { lang: "" },
  addEventListener: noop,
  getElementById(id) {
    if (id === "app") return app;
    if (id === "pop") return pop;
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
  crypto: { randomUUID: () => "runtime-test-uuid" },
  addEventListener: noop,
  scrollY: 0,
  innerWidth: 1200,
  innerHeight: 800,
  speechSynthesis: { cancel: noop, getVoices: () => [] },
  Audio: AudioStub
};
context.window = context;

vm.createContext(context);
vm.runInContext(application, context);

const runtime = context.__reviewRuntimeTest;
assert(runtime, "runtime test API was not exposed");

const bien = runtime.vocabWords.find((word) => word.w === "bien");
const con = runtime.vocabWords.find((word) => word.w === "con");
assert(bien && con, "expected bien and con in Mi Español");
assert(runtime.reviewAnswerMatches(bien, "good") === true,
  "bien should accept the contextual English answer good");
assert(runtime.reviewAnswerMatches(con, "and") === false,
  "con must not accept and; the matching Spanish connector is y");

const now = Date.now();
Object.assign(runtime.state, {
  reviewQueue: [bien],
  reviewTotal: 1,
  reviewSessionDone: 0,
  reviewSessionId: "rs:runtime-test",
  reviewRevealed: true,
  reviewAnswer: "good",
  reviewAnswerMode: "typed",
  reviewAnswerCorrect: runtime.reviewAnswerMatches(bien, "good"),
  reviewAnswerTrigger: "typed_submit",
  reviewCardStartedAt: now,
  reviewAnswerAt: now + 10,
  reviewIssueReported: false,
  reviewIssueNotice: ""
});

function reviewSnapshot() {
  return JSON.stringify({
    queue: runtime.state.reviewQueue.map(runtime.reviewCardKey),
    total: runtime.state.reviewTotal,
    done: runtime.state.reviewSessionDone,
    sessionId: runtime.state.reviewSessionId,
    revealed: runtime.state.reviewRevealed,
    answer: runtime.state.reviewAnswer,
    answerMode: runtime.state.reviewAnswerMode,
    answerCorrect: runtime.state.reviewAnswerCorrect,
    answerTrigger: runtime.state.reviewAnswerTrigger,
    cardStartedAt: runtime.state.reviewCardStartedAt,
    answerAt: runtime.state.reviewAnswerAt,
    reviewStore: runtime.reviewStore,
    events: runtime.reviewEvents(),
    reviewStorage: localStorage.getItem("fabulita.review.v1"),
    eventStorage: localStorage.getItem("fabulita.review.events.v1")
  });
}

const beforeIssue = reviewSnapshot();
runtime.reportReviewIssue();

let questions = runtime.qaQuestions();
assert(questions.length === 1, "reporting should add exactly one Q&A record");
const issue = questions[0];
assert(issue.source === "review_answer_issue", "missing structured issue source");
assert(issue.status === "open", "new answer issues should be open");
assert(issue.issueType === "accepted_answer_or_gloss", "unexpected issue type");
assert(issue.contextWord === "bien", "missing issue context word");
assert(issue.wordKey === "w:bien", "missing stable word key");
assert(issue.reviewSessionId === "rs:runtime-test", "missing review session id");
assert(issue.answerMode === "typed", "missing answer mode");
assert(issue.submittedAnswer === "good", "missing submitted answer");
assert(issue.expectedAnswer.split("|").includes("good"), "missing accepted answer snapshot");
assert(issue.reviewAnswerCorrect === true, "missing automatic verdict");
assert(issue.cardStartedAt === now, "missing card start timestamp");
assert(typeof issue.sourceRef === "string" && issue.sourceRef.includes("w:bien"),
  "missing idempotency source reference");
assert(issue.question.includes("复习答案待检查：bien"), "missing readable issue summary");
assert(issue.question.includes("我的答案：good"), "missing readable submitted answer");
assert(reviewSnapshot() === beforeIssue,
  "reporting an answer issue must not change queue, session, schedule, or review events");

const qaRoot = JSON.parse(localStorage.getItem("fabulita.qa.v1"));
const persistedScopes = Object.values(qaRoot.scopes);
assert(persistedScopes.length === 1 && persistedScopes[0].items.length === 1,
  "the structured issue should be persisted in the scoped Q&A store");

// Exercise both the UI guard and the persistent sourceRef guard.
runtime.reportReviewIssue();
assert(runtime.qaQuestions().length === 1, "a repeated click must be idempotent");
runtime.state.reviewIssueReported = false;
runtime.state.reviewIssueNotice = "";
runtime.reportReviewIssue();
assert(runtime.qaQuestions().length === 1,
  "the same review attempt must remain idempotent after transient UI state resets");
assert(reviewSnapshot() === beforeIssue,
  "idempotency checks must not mutate review state");

runtime.rateReview("hard", "button");
assert(reviewSnapshot() === beforeIssue,
  "the removed hard rating must be a complete no-op");
assert(runtime.qaQuestions().length === 1,
  "a legacy hard call must not alter answer issue records");

const oldHard = runtime.normalizeReviewEvent({
  id: "re:legacy-hard",
  type: "review_rated",
  reviewedAt: now - 1000,
  sessionId: "rs:legacy",
  word: "bien",
  answerMode: "skipped",
  rating: "hard",
  levelBefore: 0,
  levelAfter: 0
});
assert(oldHard && oldHard.rating === "hard",
  "historical hard events must still normalize");
const oldSummary = runtime.reviewHistorySummary([oldHard]);
assert(oldSummary.total === 1 && oldSummary.ratings.hard === 1,
  "historical hard events must remain in progress summaries");
const oldRows = runtime.progressHistoryRowsHtml([oldHard]);
assert(oldRows.includes("旧版中间项") && oldRows.includes("is-hard"),
  "historical hard events should render with the neutral legacy label");
"""


def test_review_issue_runtime_and_legacy_hard_compatibility(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the inline review runtime test")

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
        "Node review runtime regression failed\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
