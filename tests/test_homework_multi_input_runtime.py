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
    window.__homeworkMultiInputRuntimeTest = {
      state,
      homeworkAssignments,
      homeworkItems,
      homeworkVerdict,
      homeworkExpectedAnswer,
      homeworkBlanks,
      homeworkMultiAnswers,
      homeworkTypeLabel,
      homeworkProgress,
      homeworkStats,
      homeworkMistakeEntries,
      homeworkAttemptHistory,
      homeworkHistoryHtml,
      learningEvents,
      openHomework,
      saveHomeworkAnswer,
      checkHomeworkAnswer,
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
    crypto: (() => {
      let counter = 0;
      return { randomUUID: () => `homework-multi-input-runtime-uuid-${counter++}` };
    })(),
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
  assert(context.__homeworkMultiInputRuntimeTest,
    "runtime multi-input API was not exposed");
  return context.__homeworkMultiInputRuntimeTest;
}

const runtime = bootPage(process.argv[1]);
const quiz = runtime.homeworkAssignments.find(
  (candidate) => candidate.id === "multi-input-quiz"
);
assert(quiz, "expected the multi-input quiz assignment");

const entries = runtime.homeworkItems(quiz);
assert(entries.length === 2, "both multi-input items must survive validation");
assert(entries.every((entry) => entry.type === "multi_input"),
  "section type multi_input must map onto the multi_input entry type");
assert(runtime.homeworkTypeLabel("multi_input") === "变形题",
  "multi_input needs its own visible type label");

const first = entries[0];
assert(runtime.homeworkBlanks(first.item).length === 2,
  "each quiz row carries a casual and a formal blank");
assert(runtime.homeworkExpectedAnswer(first.item).includes("のんでいた") &&
    runtime.homeworkExpectedAnswer(first.item).includes("のんでいました"),
  "the expected answer must mention both blanks");

const bothCorrect = JSON.stringify({
  "blank-casual-nomu": "のんでいた",
  "blank-formal-nomu": "飲んでいました"
});
const oneWrong = JSON.stringify({
  "blank-casual-nomu": "のんでいる",
  "blank-formal-nomu": "のんでいました"
});
const halfEmpty = JSON.stringify({
  "blank-casual-nomu": "のんでいた",
  "blank-formal-nomu": ""
});
assert(runtime.homeworkVerdict(first.item, bothCorrect) === "correct",
  "all-correct blanks must grade correct (accepting kanji variants)");
assert(runtime.homeworkVerdict(first.item, oneWrong) === "incorrect",
  "a single wrong blank must grade incorrect");
assert(runtime.homeworkVerdict(first.item, halfEmpty) === "",
  "an empty blank must keep the item ungraded");

runtime.openHomework(quiz);
let questionHtml = runtime.dashboardHomeworkQuestionHtml(quiz);
assert((questionHtml.match(/name="homework-answer-multi"/g) || []).length === 2,
  "the form must render one input per blank");
assert(questionHtml.includes("普通体") && questionHtml.includes("丁寧体"),
  "each blank input needs its own label");
assert(questionHtml.includes("历史记录（0 次作答）"),
  "an untouched question must show an empty attempt history toggle");

assert(runtime.checkHomeworkAnswer(halfEmpty) === false,
  "checking with an empty blank must be rejected");
assert(runtime.checkHomeworkAnswer(oneWrong) === true,
  "a graded wrong answer still saves");
let progress = runtime.homeworkProgress(quiz);
let response = progress.responses[first.item.id];
assert(response.status === "incorrect" && response.firstStatus === "incorrect",
  "the overall verdict and first-attempt verdict must persist");

questionHtml = runtime.dashboardHomeworkQuestionHtml(quiz);
assert(questionHtml.includes("homework-blank-results"),
  "graded multi-input feedback must list per-blank results");
assert(questionHtml.includes("正解：のんでいた"),
  "a wrong blank must reveal its expected answer");
assert(questionHtml.includes("✓"), "a correct blank must be marked as such");

assert(runtime.checkHomeworkAnswer(bothCorrect) === true,
  "correcting the answer must save again");
progress = runtime.homeworkProgress(quiz);
response = progress.responses[first.item.id];
assert(response.status === "correct" && response.firstStatus === "incorrect",
  "first-attempt scoring must survive the corrected retry");

const blankEvents = runtime.learningEvents().filter(
  (event) => event.entityId === "blank-casual-nomu"
);
assert(blankEvents.length === 2,
  "every check must record one event per blank under the blank id");
const firstBlankEvent = blankEvents.find((event) => event.attempt === 1);
const secondBlankEvent = blankEvents.find((event) => event.attempt === 2);
assert(firstBlankEvent && firstBlankEvent.verdict === "incorrect" &&
    secondBlankEvent && secondBlankEvent.verdict === "correct",
  "per-blank events must carry per-blank verdicts");
assert(blankEvents.every((event) => event.homeworkItemId === first.item.id),
  "per-blank events must point back to their parent item");

const history = runtime.homeworkAttemptHistory(quiz, first.item);
assert(history.length === 4,
  "multi-input history lists the per-blank attempts, not the JSON envelope");
assert(history.every((attempt) => attempt.label),
  "multi-input history rows must be labelled with their blank");
assert(history.some((attempt) => attempt.answer === "のんでいる" &&
    attempt.verdict === "incorrect"),
  "history must retain the wrong first attempt verbatim");

runtime.state.homeworkHistoryOpenId = first.item.id;
const historyHtml = runtime.homeworkHistoryHtml(quiz, first);
assert(historyHtml.includes("homework-history-list") &&
    historyHtml.includes("のんでいる"),
  "the open history panel must render past answers");
assert(historyHtml.includes("AI 分析这道题"),
  "the history panel must offer AI analysis");

const mistakes = runtime.homeworkMistakeEntries();
assert(mistakes.length === 1 && mistakes[0].entry.item.id === first.item.id,
  "a wrong first attempt must land in the mistake book");
"""


def _write_project(project_root: Path) -> Project:
    project_root.mkdir()
    (project_root / "stories").mkdir()
    (project_root / "fabulita.json").write_text(
        json.dumps(
            {
                "name": "Multi Input Test",
                "lang": "ja",
                "gloss_lang": "zh",
                "ui_default": "zh",
                "homework_id": "multi-input-test",
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
                "id": "multi-input-quiz",
                "title": "变形测验",
                "sections": [
                    {
                        "id": "quiz",
                        "type": "multi_input",
                        "title": "Quiz ① ～ていた / ～ていました",
                        "instructions": "左格填普通体，右格填丁寧体。",
                        "items": [
                            {
                                "id": "row-nomu",
                                "number": 1,
                                "prompt": "のむ → ______ ・ ______",
                                "blanks": [
                                    {
                                        "id": "blank-casual-nomu",
                                        "label": "普通体 Casual",
                                        "answers": ["のんでいた", "飲んでいた"],
                                        "canonicalAnswer": "のんでいた",
                                    },
                                    {
                                        "id": "blank-formal-nomu",
                                        "label": "丁寧体 Formal",
                                        "answers": ["のんでいました", "飲んでいました"],
                                        "canonicalAnswer": "のんでいました",
                                    },
                                ],
                            },
                            {
                                "id": "row-taberu",
                                "number": 2,
                                "prompt": "たべる → ______ ・ ______",
                                "blanks": [
                                    {
                                        "id": "blank-casual-taberu",
                                        "label": "普通体 Casual",
                                        "answers": ["たべていた", "食べていた"],
                                        "canonicalAnswer": "たべていた",
                                    },
                                    {
                                        "id": "blank-formal-taberu",
                                        "label": "丁寧体 Formal",
                                        "answers": ["たべていました", "食べていました"],
                                        "canonicalAnswer": "たべていました",
                                    },
                                ],
                            },
                        ],
                    }
                ],
            }
        ]
    }
    (project_root / "homework.json").write_text(
        json.dumps(homework, ensure_ascii=False), encoding="utf-8"
    )
    return Project(project_root)


def test_homework_multi_input_runtime(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the multi-input homework runtime test")

    project = _write_project(tmp_path / "multi-input")
    page, _, _, _ = build.build(
        project,
        out=tmp_path / "multi-input.html",
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
        "Node homework multi-input regression failed\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
