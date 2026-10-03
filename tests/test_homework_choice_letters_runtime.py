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
    window.__homeworkChoiceLetterRuntimeTest = {
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
      checkHomeworkAnswer,
      selectHomeworkOptionByLetter
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
    crypto: { randomUUID: () => "homework-choice-letter-runtime-uuid" },
    addEventListener: noop,
    scrollY: 0,
    scrollX: 0,
    innerWidth: 1200,
    innerHeight: 800,
    speechSynthesis: { cancel: noop, getVoices: () => [], speak: noop },
    SpeechSynthesisUtterance: class { constructor(text) { this.text = text; } },
    Audio: AudioStub
  };
  context.window = context;

  vm.createContext(context);
  vm.runInContext(application, context);
  assert(context.__homeworkChoiceLetterRuntimeTest,
    "runtime choice-letter API was not exposed");
  return {
    runtime: context.__homeworkChoiceLetterRuntimeTest,
    localStorage
  };
}

const page = bootPage(process.argv[1]);
const runtime = page.runtime;
const assignment = runtime.homeworkAssignments.find(
  (candidate) => candidate.id === "ejercicios-vocabulario-a1-1"
);
assert(assignment, "expected the A1 vocabulary homework assignment");
runtime.openHomework(assignment);
runtime.state.homeworkIndex = 0;
const entry = runtime.homeworkItems(assignment)[0];
assert(entry.type === "single_choice" && entry.item.options.length === 3,
  "first item should be a three-option choice question");

const html = runtime.dashboardHomeworkQuestionHtml(assignment);
["A", "B", "C"].forEach((letter) => {
  assert(html.includes('<span class="homework-option-letter" aria-hidden="true">' + letter + "</span>"),
    "option " + letter + " should carry a letter badge");
});
assert(!html.includes('homework-option-letter" aria-hidden="true">D<'),
  "a three-option question must not render a D badge");
assert(html.includes('aria-label="' + "B. " + entry.item.options[1] + '"'),
  "each option label should be announced with its letter");

assert(runtime.selectHomeworkOptionByLetter("b") === true, "lowercase b should select option B");
let progress = runtime.homeworkProgress(assignment);
assert(progress.responses[entry.item.id].answer === entry.item.options[1],
  "selecting B should save the second option as the draft answer");

assert(runtime.selectHomeworkOptionByLetter("D") === false, "D is out of range for three options");
progress = runtime.homeworkProgress(assignment);
assert(progress.responses[entry.item.id].answer === entry.item.options[1],
  "an out-of-range letter must not change the draft");

assert(runtime.selectHomeworkOptionByLetter("A") === true, "A should select option A");
assert(runtime.homeworkProgress(assignment).responses[entry.item.id].answer === entry.item.options[0],
  "selecting A should save the first option");

const selectedHtml = runtime.dashboardHomeworkQuestionHtml(assignment);
assert(selectedHtml.includes('value="' + entry.item.options[0] + '" checked'),
  "the rendered radio for A should be checked after keyboard selection");

const textEntryIndex = runtime.homeworkItems(assignment).findIndex((candidate) => candidate.type === "text_input");
assert(textEntryIndex !== -1, "expected a text item to test the guard");
runtime.state.homeworkIndex = textEntryIndex;
assert(runtime.selectHomeworkOptionByLetter("A") === false,
  "letters must be ignored on non-choice questions");
console.log("homework choice letter runtime checks passed");
"""


def test_homework_choice_letters_runtime(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the inline homework choice-letter test")

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
        "Node homework choice-letter regression failed\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
