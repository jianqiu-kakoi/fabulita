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
    window.__homeworkTypeNavigationRuntimeTest = {
      state,
      homeworkAssignments,
      homeworkItems,
      homeworkActiveItems,
      homeworkProgress,
      homeworkAvailableTypes,
      homeworkTypeStats,
      homeworkTypePosition,
      jumpHomeworkType,
      homeworkNextTarget,
      dashboardHomeworkTypeProgressHtml,
      homeworkReferenceTablesHtml,
      dashboardHomeworkListHtml,
      dashboardHomeworkQuestionHtml,
      openHomework,
      saveHomeworkAnswer,
      checkHomeworkAnswer
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
    crypto: { randomUUID: () => "homework-type-navigation-runtime-uuid" },
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
  assert(context.__homeworkTypeNavigationRuntimeTest,
    "runtime type-navigation API was not exposed");
  return {
    runtime: context.__homeworkTypeNavigationRuntimeTest,
    localStorage
  };
}

const page = bootPage(process.argv[1]);
const runtime = page.runtime;
const vocabularyAssignment = runtime.homeworkAssignments.find(
  (candidate) => candidate.id === "ejercicios-vocabulario-a1-1"
);
const conjugationAssignment = runtime.homeworkAssignments.find(
  (candidate) => candidate.id === "ser-estar-conjugation-a1"
);
assert(vocabularyAssignment, "expected the A1 vocabulary homework assignment");
assert(conjugationAssignment, "expected the Ser/Estar conjugation assignment");

const vocabularyItems = runtime.homeworkItems(vocabularyAssignment);
assert(vocabularyItems.length === 50, "the vocabulary assignment should have 50 items");
assert(runtime.homeworkAvailableTypes(vocabularyAssignment).join("|") ===
    "single_choice|text_input",
  "the vocabulary assignment should expose both question types in source order");

runtime.openHomework(vocabularyAssignment);
for (let index = 0; index < 10; index += 1) {
  runtime.state.homeworkIndex = index;
  const answer = vocabularyItems[index].item.answers[0];
  assert(runtime.saveHomeworkAnswer(answer).saved === true,
    "each of the first ten choice drafts should save");
  assert(runtime.checkHomeworkAnswer() === true,
    "each of the first ten choices should be checkable");
}

let progress = runtime.homeworkProgress(vocabularyAssignment);
let choiceStats = runtime.homeworkTypeStats(
  vocabularyAssignment, progress, "single_choice"
);
let textStats = runtime.homeworkTypeStats(
  vocabularyAssignment, progress, "text_input"
);
assert(choiceStats.total === 30 && choiceStats.checked === 10,
  "choice progress should report 10 / 30 checked");
assert(textStats.total === 20 && textStats.checked === 0,
  "text progress should report 0 / 20 checked");

let progressHtml = runtime.dashboardHomeworkTypeProgressHtml(vocabularyAssignment);
assert(progressHtml.includes("总进度 10 / 50 已检查"),
  "the switcher should retain the overall checked count");
assert(progressHtml.includes("选择题") && progressHtml.includes("10 / 30 已检查") &&
    progressHtml.includes('data-homework-type="single_choice"'),
  "the switcher should render actionable choice progress");
assert(progressHtml.includes("填空题") && progressHtml.includes("0 / 20 已检查") &&
    progressHtml.includes('data-homework-type="text_input"'),
  "the switcher should render actionable text progress");

assert(runtime.jumpHomeworkType(vocabularyAssignment, "text_input") === true,
  "the learner should be able to jump directly to text input");
assert(runtime.state.homeworkIndex === 30,
  "the first text input should retain its global item index");
assert(runtime.homeworkActiveItems(vocabularyAssignment)[30].item.id === "p2-01",
  "jumping to text input should open p2-01");
progress = runtime.homeworkProgress(vocabularyAssignment);
assert(progress.currentItemId === "p2-01",
  "the type jump should persist the stable current item id");
let position = runtime.homeworkTypePosition(vocabularyAssignment);
assert(position.type === "text_input" && position.position === 0 &&
    position.total === 20,
  "the first text input should be position 1 of 20 internally");
let nextTarget = runtime.homeworkNextTarget(vocabularyAssignment);
assert(nextTarget.index === 31 && nextTarget.label === "下一题",
  "next from p2-01 should stay within the text-input section");

assert(runtime.jumpHomeworkType(vocabularyAssignment, "single_choice") === true,
  "the learner should be able to jump back to choices");
assert(runtime.state.homeworkIndex === 10,
  "jumping back should select the first unchecked choice, not restart");
assert(runtime.homeworkActiveItems(vocabularyAssignment)[10].item.id === "p1-11",
  "the first unchecked choice after ten answers should be p1-11");
progress = runtime.homeworkProgress(vocabularyAssignment);
assert(progress.currentItemId === "p1-11",
  "jumping back should persist p1-11 as the current item");
position = runtime.homeworkTypePosition(vocabularyAssignment);
assert(position.type === "single_choice" && position.position === 10 &&
    position.total === 30,
  "p1-11 should be position 11 of 30 internally");
choiceStats = runtime.homeworkTypeStats(
  vocabularyAssignment, progress, "single_choice"
);
textStats = runtime.homeworkTypeStats(
  vocabularyAssignment, progress, "text_input"
);
assert(choiceStats.checked === 10 && textStats.checked === 0,
  "type switching must not mutate checked answers");

runtime.state.homeworkIndex = 29;
nextTarget = runtime.homeworkNextTarget(vocabularyAssignment);
assert(nextTarget.index === 30 && nextTarget.label === "去做填空题",
  "finishing the choice section should target the first incomplete text item");

const conjugationItems = runtime.homeworkItems(conjugationAssignment);
assert(conjugationItems.length === 12,
  "the Ser/Estar assignment should have twelve text-input items");
assert(runtime.homeworkAvailableTypes(conjugationAssignment).join("|") === "text_input",
  "a text-only assignment must expose exactly one available type");
runtime.openHomework(conjugationAssignment);
assert(runtime.state.homeworkIndex === 0,
  "a fresh text-only assignment should open its first item");
progress = runtime.homeworkProgress(conjugationAssignment);
choiceStats = runtime.homeworkTypeStats(
  conjugationAssignment, progress, "single_choice"
);
textStats = runtime.homeworkTypeStats(
  conjugationAssignment, progress, "text_input"
);
assert(choiceStats.total === 0 && choiceStats.checked === 0,
  "the absent choice type should remain an internal zero-only stat");
assert(textStats.total === 12 && textStats.checked === 0,
  "the only visible type should report 0 / 12 checked");

const conjugationListHtml = runtime.dashboardHomeworkListHtml();
assert(conjugationListHtml.includes("Ser 和 Estar 变位练习 A1") &&
    conjugationListHtml.includes("12 道填空题"),
  "the assignment list should expose the new conjugation exercise");
const referenceHtml = runtime.homeworkReferenceTablesHtml(conjugationAssignment);
assert(referenceHtml.includes("Ser：身份、职业、较稳定特征") &&
    referenceHtml.includes("Estar：位置、当前状态") &&
    referenceHtml.includes("nosotros / nosotras") &&
    referenceHtml.includes("somos") &&
    referenceHtml.includes("estamos") &&
    referenceHtml.includes("estáis"),
  "the exercise should render both complete reference tables");
const conjugationQuestionHtml =
  runtime.dashboardHomeworkQuestionHtml(conjugationAssignment);
assert(conjugationQuestionHtml.includes("yo → ser") &&
    conjugationQuestionHtml.includes("当前题目 1 / 12"),
  "the conjugation exercise should open with the first Ser prompt");

progressHtml = runtime.dashboardHomeworkTypeProgressHtml(conjugationAssignment);
assert(progressHtml.includes("填空题") && progressHtml.includes("0 / 12 已检查") &&
    progressHtml.includes('data-homework-type="text_input"'),
  "the text-only assignment should render its text progress");
assert(!progressHtml.includes("选择题") &&
    !progressHtml.includes('data-homework-type="single_choice"'),
  "the text-only assignment must not render an empty choice entry");
assert(runtime.jumpHomeworkType(conjugationAssignment, "single_choice") === false,
  "jumping to an unavailable type should be a safe no-op");
assert(runtime.state.homeworkIndex === 0,
  "an unavailable-type jump must not disturb the current item");
assert(runtime.jumpHomeworkType(conjugationAssignment, "text_input") === true,
  "the available type should remain directly selectable");
position = runtime.homeworkTypePosition(conjugationAssignment);
assert(position.type === "text_input" && position.position === 0 &&
    position.total === 12,
  "the text-only assignment should report position 1 of 12 internally");
nextTarget = runtime.homeworkNextTarget(conjugationAssignment);
assert(nextTarget.index === 1 && nextTarget.label === "下一题",
  "next navigation should work normally within the only available type");
"""


def test_homework_type_progress_and_navigation_runtime(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the inline homework type-navigation test")

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
        "Node homework type-navigation regression failed\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
