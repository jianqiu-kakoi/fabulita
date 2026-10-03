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
    window.__homeworkAudioFeedbackRuntimeTest = {
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
      selectHomeworkOptionByLetter,
      speakHomeworkOption,
      stopAll,
      speechEngineStuck,
      dashboardHomeworkQuestionHtml
    };
  ` + application.slice(close);

  const spoken = [];
  const tones = [];
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
    crypto: { randomUUID: () => "homework-audio-feedback-runtime-uuid" },
    addEventListener: noop,
    scrollY: 0,
    scrollX: 0,
    innerWidth: 1200,
    innerHeight: 800,
    speechSynthesis: {
      speaking: false,
      pending: false,
      cancel() { spoken.push({ text: "<cancel>", lang: "" }); this.speaking = false; this.pending = false; },
      getVoices: () => [{ lang: "es-ES", name: "Stub Spanish" }],
      speak(utterance) {
        spoken.push({ text: utterance.text, lang: utterance.lang, utterance });
        this.speaking = true;
      }
    },
    SpeechSynthesisUtterance: class { constructor(text) { this.text = text; } },
    AudioContext: class {
      constructor() { this.currentTime = 0; this.destination = {}; this.state = "running"; }
      resume() { return Promise.resolve(); }
      createOscillator() {
        const osc = { type: "sine", frequency: { value: 0 }, connect() {}, start() {}, stop() {} };
        tones.push(osc);
        return osc;
      }
      createGain() {
        return { gain: { value: 1, setValueAtTime() {}, exponentialRampToValueAtTime() {}, linearRampToValueAtTime() {} }, connect() {} };
      }
    },
    Audio: AudioStub
  };
  context.window = context;

  vm.createContext(context);
  vm.runInContext(application, context);
  assert(context.__homeworkAudioFeedbackRuntimeTest,
    "runtime audio-feedback API was not exposed");
  return {
    runtime: context.__homeworkAudioFeedbackRuntimeTest,
    localStorage,
    spoken,
    tones,
    context
  };
}

(async () => {
const page = bootPage(process.argv[1]);
const runtime = page.runtime;
const spoken = page.spoken;
const tones = page.tones;
const assignment = runtime.homeworkAssignments.find(
  (candidate) => candidate.id === "ejercicios-vocabulario-a1-1"
);
assert(assignment, "expected the A1 vocabulary homework assignment");
runtime.openHomework(assignment);
runtime.state.homeworkIndex = 0;
const entry = runtime.homeworkItems(assignment)[0];
assert(entry.type === "single_choice", "first item should be a choice question");

assert(runtime.selectHomeworkOptionByLetter("B") === true, "B should select");
const spokenTexts = spoken.map((event) => event.text).filter((text) => text !== "<cancel>");
assert(spokenTexts.length === 1 && spokenTexts[0] === entry.item.options[1],
  "selecting an option should speak that option, got " + JSON.stringify(spoken));
assert(spoken[spoken.length - 1].text !== "<cancel>",
  "keyboard selection must not cancel speech after starting it (render() calls stopAll), got " +
  JSON.stringify(spoken));

// grading sounds
const correctAnswer = entry.item.answers[0];
const wrongAnswer = entry.item.options.find((option) => option !== correctAnswer);
tones.length = 0;
assert(runtime.checkHomeworkAnswer(wrongAnswer) === true, "wrong answer should still be checkable");
assert(tones.length >= 1, "a wrong answer should play a tone");
const wrongFreqs = tones.map((osc) => osc.frequency.value);
assert(wrongFreqs.every((f) => f > 0 && f < 400),
  "the wrong tone should be low, got " + JSON.stringify(wrongFreqs));

tones.length = 0;
assert(runtime.checkHomeworkAnswer(correctAnswer) === true, "correct answer should be checkable");
assert(tones.length >= 2, "a correct answer should play an ascending pair of notes");
const rightFreqs = tones.map((osc) => osc.frequency.value);
assert(rightFreqs[0] >= 500 && rightFreqs[1] > rightFreqs[0],
  "the correct tones should be bright and ascending, got " + JSON.stringify(rightFreqs));

// A word being spoken must not be cancelled by the re-render that follows
// "check answer": Chrome on macOS can wedge its speech engine when cancel()
// interrupts an active utterance. Idle engines are not cancelled either.
spoken.length = 0;
runtime.state.homeworkIndex = 0;
runtime.speakHomeworkOption(assignment, runtime.homeworkItems(assignment)[0], entry.item.options[0]);
assert(spoken.length === 1 && spoken[0].text === entry.item.options[0],
  "speakHomeworkOption should speak the word without a preceding cancel, got " + JSON.stringify(spoken.map((e) => e.text)));
runtime.stopAll();
assert(!spoken.some((event) => event.text === "<cancel>"),
  "stopAll must let a short word finish instead of cancelling it, got " + JSON.stringify(spoken.map((e) => e.text)));
const wordUtterance = spoken[0].utterance;
wordUtterance.onstart && wordUtterance.onstart();
wordUtterance.onend && wordUtterance.onend();
page.context.speechSynthesis.speaking = false;
spoken.length = 0;
runtime.stopAll();
assert(spoken.length === 0, "stopAll must not call cancel() when nothing is speaking");
page.context.speechSynthesis.speaking = true;
runtime.stopAll();
assert(spoken.length === 1 && spoken[0].text === "<cancel>",
  "stopAll still cancels long-running (non-word) speech once the word window has passed");
page.context.speechSynthesis.speaking = false;

// If an utterance never starts, the engine is wedged: surface a hint.
spoken.length = 0;
assert(runtime.speechEngineStuck() === false, "engine should not be flagged before any timeout");
runtime.speakHomeworkOption(assignment, runtime.homeworkItems(assignment)[0], entry.item.options[1]);
await new Promise((resolve) => setTimeout(resolve, 2300));
assert(runtime.speechEngineStuck() === true, "an utterance with no onstart after 2s should flag the engine as stuck");
const stuckHtml = runtime.dashboardHomeworkQuestionHtml(assignment);
assert(stuckHtml.includes("完全退出"), "the homework sheet should tell the learner to fully quit Chrome");

// English-answer options must not be read with the Spanish voice
const englishAssignment = runtime.homeworkAssignments.find((candidate) =>
  runtime.homeworkItems(candidate).some((item) =>
    item.type === "single_choice" && item.item.answerLanguage && item.item.answerLanguage !== "es"));
if (englishAssignment) {
  runtime.openHomework(englishAssignment);
  runtime.state.homeworkIndex = runtime.homeworkItems(englishAssignment).findIndex((item) =>
    item.type === "single_choice" && item.item.answerLanguage && item.item.answerLanguage !== "es");
  spoken.length = 0;
  assert(runtime.selectHomeworkOptionByLetter("A") === true, "English option should still select");
  assert(spoken.every((event) => event.text === "<cancel>"),
    "English options must not be spoken with the Spanish voice");
  console.log("english guard exercised");
} else {
  console.log("english guard skipped: no English-answer choice in public homework");
}
console.log("homework audio feedback runtime checks passed");
})().catch((error) => { console.error(error); process.exit(1); });
"""


def test_homework_audio_feedback_runtime(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the inline homework audio-feedback test")

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
        include_local_homework=(project_root / "homework.local.json").exists(),
    )

    result = subprocess.run(
        [node, "-e", NODE_RUNTIME_TEST, str(page)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        "Node homework audio-feedback regression failed\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
