import json
import shutil
import subprocess
from pathlib import Path

import pytest

from fabulita import build
from fabulita.project import Project


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
    window.__homeworkSelfReviewRuntimeTest = {
      state,
      homeworkAssignments,
      homeworkItems,
      homeworkVerdict,
      homeworkProgress,
      homeworkStats,
      homeworkTypeStats,
      homeworkAvailableTypes,
      homeworkTypeLabel,
      homeworkNextTarget,
      jumpHomeworkType,
      homeworkMistakeEntries,
      learningEvents,
      openHomework,
      saveHomeworkAnswer,
      checkHomeworkAnswer,
      finishHomeworkSequence,
      retryHomeworkAnswers,
      dashboardHomeworkListHtml,
      dashboardHomeworkQuestionHtml,
      dashboardHomeworkSummaryHtml,
      dashboardHomeworkTypeProgressHtml
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
    crypto: { randomUUID: () => "homework-self-review-runtime-uuid" },
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
  assert(context.__homeworkSelfReviewRuntimeTest,
    "runtime self-review API was not exposed");
  return context.__homeworkSelfReviewRuntimeTest;
}

const runtime = bootPage(process.argv[1]);
const selfReview = runtime.homeworkAssignments.find(
  (candidate) => candidate.id === "self-review-only"
);
assert(selfReview, "expected the self-review assignment");

runtime.openHomework(selfReview);
const selfEntry = runtime.homeworkItems(selfReview)[0];
assert(selfEntry.type === "open_response", "self-review item must be an open response");
assert(runtime.homeworkTypeLabel(selfEntry.type) === "开放题",
  "open response needs a visible type label");
assert(runtime.homeworkVerdict(selfEntry.item, "") === "",
  "blank open responses must remain unsubmitted");
assert(runtime.homeworkVerdict(selfEntry.item, "。") === "self_reviewed",
  "every non-empty self-review response should be accepted without grading");
assert(runtime.checkHomeworkAnswer("   ") === false,
  "blank open responses must not be saved as complete");

let questionHtml = runtime.dashboardHomeworkQuestionHtml(selfReview);
assert(questionHtml.includes("<textarea") && questionHtml.includes("is-open-response"),
  "open responses should use a multiline answer field");
assert(questionHtml.includes("开放题") && questionHtml.includes("保存并查看参考"),
  "open response UI needs its own type and submit labels");
assert(!questionHtml.includes("检查答案"),
  "self-review submit UI must not promise automatic grading");

const learnerAnswer = "公園で写真を撮りました。";
runtime.saveHomeworkAnswer(learnerAnswer);
assert(runtime.checkHomeworkAnswer() === true,
  "any non-empty self-review response should save");

let progress = runtime.homeworkProgress(selfReview);
let response = progress.responses[selfEntry.item.id];
assert(response.answer === learnerAnswer, "the learner response must persist unchanged");
assert(response.status === "self_reviewed", "self-review needs a distinct status");
assert(response.firstStatus === undefined,
  "a non-graded response must not create a first-attempt verdict");
assert(response.meaningCorrect === undefined,
  "a non-graded response must not be marked meaning-correct or meaning-wrong");

const stats = runtime.homeworkStats(selfReview, progress);
assert(stats.total === 1 && stats.checked === 1 && stats.selfReviewed === 1,
  "self-review should count as completed progress");
assert(stats.correct === 0 && stats.near === 0 && stats.incorrect === 0,
  "self-review must not enter graded score buckets");
assert(stats.firstCorrect === 0 && stats.firstNear === 0 && stats.firstIncorrect === 0,
  "self-review must not enter first-attempt score buckets");

questionHtml = runtime.dashboardHomeworkQuestionHtml(selfReview);
assert(questionHtml.includes("已保存，请自行对照"),
  "saved feedback should explicitly request self-checking");
assert(questionHtml.includes("参考作答：図書館で本を読みました。"),
  "feedback should prefer canonicalAnswer for the model answer");
assert(questionHtml.includes("参考翻译：我在图书馆读了书。"),
  "feedback should show answerTranslation when supplied");
assert(!questionHtml.includes("答对了") && !questionHtml.includes("暂时不对"),
  "self-review feedback must not claim correct or incorrect");

const progressHtml = runtime.dashboardHomeworkTypeProgressHtml(selfReview);
assert(progressHtml.includes("开放题") && progressHtml.includes("1 / 1 已保存"),
  "open-response progress should use saved, not graded, language");

const answerEvent = runtime.learningEvents().find(
  (event) => event.source === "homework" && event.action === "answer_checked"
);
assert(answerEvent && answerEvent.verdict === "self_reviewed" &&
    answerEvent.answerMode === "self_review",
  "the audit event must retain the non-graded mode and verdict");
assert(answerEvent.answerCorrect === null && answerEvent.meaningCorrect === null,
  "the audit event must not encode self-review as false grading");

runtime.finishHomeworkSequence(selfReview);
progress = runtime.homeworkProgress(selfReview);
assert(progress.completedAt > 0, "a saved open response should allow completion");
const summary = runtime.dashboardHomeworkSummaryHtml(selfReview);
assert(summary.includes("开放题已保存") && summary.includes("请对照参考作答自行核对"),
  "the summary must describe saved self-review work");
assert(!summary.includes("重做未完全答对") && !summary.includes("暂时不对"),
  "self-review must not appear in retry or incorrect summary UI");

runtime.retryHomeworkAnswers(selfReview);
progress = runtime.homeworkProgress(selfReview);
assert(progress.responses[selfEntry.item.id].status === "self_reviewed",
  "retry flow must leave self-reviewed responses intact");
assert(runtime.homeworkMistakeEntries().length === 0,
  "self-reviewed responses must never enter the mistake book");

const threeTypes = runtime.homeworkAssignments.find(
  (candidate) => candidate.id === "three-types"
);
assert(threeTypes, "expected the three-type navigation fixture");
assert(runtime.homeworkAvailableTypes(threeTypes).join("|") ===
    "single_choice|open_response|text_input",
  "type discovery must preserve all three homework types");
runtime.openHomework(threeTypes);
let next = runtime.homeworkNextTarget(threeTypes);
assert(next.index === 1 && next.label.includes("开放题"),
  "navigation should move from choices to open responses");
assert(runtime.jumpHomeworkType(threeTypes, "open_response") === true &&
    runtime.state.homeworkIndex === 1,
  "direct type navigation should support open responses");
next = runtime.homeworkNextTarget(threeTypes);
assert(next.index === 2 && next.label.includes("填空题"),
  "navigation should continue from open responses to text inputs");

const listHtml = runtime.dashboardHomeworkListHtml();
assert(listHtml.includes("1 道选择题") && listHtml.includes("1 道开放题") &&
    listHtml.includes("1 道填空题"),
  "assignment metadata should count all three types separately");
"""


def _write_project(project_root: Path) -> Project:
    project_root.mkdir()
    (project_root / "stories").mkdir()
    (project_root / "fabulita.json").write_text(
        json.dumps(
            {
                "name": "Self Review Test",
                "lang": "ja",
                "gloss_lang": "zh",
                "ui_default": "zh",
                "homework_id": "self-review-test",
                "layout": "vocab",
                "tts": {"backend": "none", "voice": "ja-JP-NanamiNeural"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (project_root / "vocab.json").write_text('{"words": []}', encoding="utf-8")
    (project_root / "glossary.json").write_text("{}", encoding="utf-8")
    homework = {
        "assignments": [
            {
                "id": "self-review-only",
                "title": "开放题自查",
                "sections": [
                    {
                        "id": "open",
                        "type": "open_response",
                        "title": "完整句回答",
                        "instructions": "写出自己的回答，再对照参考作答。",
                        "items": [
                            {
                                "id": "open-1",
                                "prompt": "自由回答を書いてください。",
                                "answerMode": "self_review",
                                "answers": ["备用参考"],
                                "canonicalAnswer": "図書館で本を読みました。",
                                "answerTranslation": "我在图书馆读了书。",
                            }
                        ],
                    }
                ],
            },
            {
                "id": "three-types",
                "title": "三种题型",
                "sections": [
                    {
                        "id": "choice",
                        "type": "single_choice",
                        "items": [
                            {
                                "id": "choice-1",
                                "prompt": "Choice",
                                "options": ["a", "b"],
                                "answers": ["a"],
                            }
                        ],
                    },
                    {
                        "id": "open",
                        "type": "open_response",
                        "items": [
                            {
                                "id": "open-2",
                                "prompt": "Open",
                                "answerMode": "self_review",
                                "answers": ["model"],
                            }
                        ],
                    },
                    {
                        "id": "text",
                        "type": "text_input",
                        "items": [
                            {"id": "text-1", "prompt": "Text", "answers": ["answer"]}
                        ],
                    },
                ],
            },
        ]
    }
    (project_root / "homework.json").write_text(
        json.dumps(homework, ensure_ascii=False), encoding="utf-8"
    )
    return Project(project_root)


def test_homework_self_review_runtime(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the inline homework self-review test")

    project = _write_project(tmp_path / "self-review")
    page, _, _, _ = build.build(
        project,
        out=tmp_path / "self-review.html",
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
        "Node homework self-review regression failed\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
