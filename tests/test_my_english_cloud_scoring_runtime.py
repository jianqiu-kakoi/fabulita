import shutil
import subprocess
from pathlib import Path

import pytest

from fabulita import build, vocab
from fabulita.project import Project


REPO = Path(__file__).parent.parent
MY_ENGLISH = REPO / "examples" / "my-english"


NODE_RUNTIME_TEST = r"""
const fs = require("fs");
const vm = require("vm");

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function answerEvents(runtime, assignmentId, itemId) {
  return runtime.learningEvents().filter((event) =>
    event.source === "homework" &&
    event.action === "answer_checked" &&
    event.assignmentId === assignmentId &&
    event.entityId === itemId
  );
}

function newAnswerEvents(runtime, previousIds, assignmentId, itemId) {
  return answerEvents(runtime, assignmentId, itemId).filter(
    (event) => !previousIds.has(event.id)
  );
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
  window.__cloudScoringRuntimeTest = {
    state,
    homeworkAssignments,
    homeworkById,
    homeworkActiveItems,
    homeworkVerdict,
    homeworkProgress,
    learningEvents,
    openHomework,
    startHomeworkScenarioExercise,
    checkHomeworkAnswerEnhanced
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

let uuidSequence = 0;
const context = {
  P,
  console,
  localStorage,
  document,
  location: { hash: "", search: "", reload: noop },
  navigator: {},
  setTimeout,
  clearTimeout,
  Intl,
  Date,
  Math,
  JSON,
  URLSearchParams,
  Blob: class BlobStub {},
  URL: { createObjectURL: () => "", revokeObjectURL: noop },
  crypto: {
    randomUUID() {
      uuidSequence += 1;
      return "cloud-score-runtime-" + uuidSequence;
    }
  },
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

(async () => {
  const runtime = context.__cloudScoringRuntimeTest;
  assert(runtime, "runtime test API was not exposed");

  const hotel = runtime.homeworkById("hotel-check-in-a1");
  assert(hotel, "hotel check-in assignment is missing");
  runtime.openHomework(hotel);
  runtime.startHomeworkScenarioExercise(hotel);

  const items = runtime.homeworkActiveItems(hotel);
  assert(items.length === 6, "expected the six hotel dialogue items");

  // Local correct and meaning-correct near-miss answers must never spend an
  // LLM request. Both still commit exactly one immutable answer attempt.
  runtime.state.homeworkIndex = 4;
  const wifiItem = items[4].item;
  let scoreCalls = 0;
  context.fabulitaLearningServices = {
    scoreAnswer() {
      scoreCalls += 1;
      return Promise.reject(new Error("this service should not be called"));
    }
  };

  let knownIds = new Set(runtime.learningEvents().map((event) => event.id));
  assert(
    await runtime.checkHomeworkAnswerEnhanced(
      "Could I have the Wi-Fi password, please?"
    ) === true,
    "the locally correct answer should save"
  );
  let created = newAnswerEvents(runtime, knownIds, hotel.id, wifiItem.id);
  assert(created.length === 1, "local correct should record one answer attempt");
  assert(created[0].verdict === "correct" && created[0].scoringSource === "local",
    "local correct should retain the local verdict source");
  assert(scoreCalls === 0, "local correct must not call the scoring service");

  knownIds = new Set(runtime.learningEvents().map((event) => event.id));
  assert(
    await runtime.checkHomeworkAnswerEnhanced("What is wifi password") === true,
    "the local near-miss answer should save"
  );
  created = newAnswerEvents(runtime, knownIds, hotel.id, wifiItem.id);
  assert(created.length === 1, "local near-miss should record one answer attempt");
  assert(
    created[0].verdict === "near_miss" &&
    created[0].meaningCorrect === true &&
    created[0].scoringSource === "local",
    "meaning-correct near-miss should remain a local result"
  );
  assert(scoreCalls === 0, "local near-miss must not call the scoring service");

  // A locally incorrect free-text answer may be upgraded by the server. The
  // provisional local result must not be persisted as a second attempt.
  runtime.state.homeworkIndex = 1;
  const reservationItem = items[1].item;
  const remoteAnswer = "Please use the surname C H E N.";
  assert(runtime.homeworkVerdict(reservationItem, remoteAnswer) === "incorrect",
    "remote-grade fixture must first fail the local matcher");
  context.fabulitaLearningServices = {
    scoreAnswer(payload) {
      scoreCalls += 1;
      assert(payload.assignmentId === hotel.id, "wrong assignment sent to scorer");
      assert(payload.itemId === reservationItem.id, "wrong item sent to scorer");
      assert(payload.learnerAnswer === remoteAnswer, "wrong answer sent to scorer");
      return Promise.resolve({
        verdict: "near_miss",
        meaningCorrect: true,
        feedbackZh: "意思正确；姓名可以直接连写为 Chen。",
        suggestedAnswer: "The reservation is under the name Chen.",
        scoringSource: "llm",
        modelVersion: "test-model",
        rubricVersion: "hotel-v1"
      });
    }
  };

  const callsBeforeRemote = scoreCalls;
  knownIds = new Set(runtime.learningEvents().map((event) => event.id));
  assert(await runtime.checkHomeworkAnswerEnhanced(remoteAnswer) === true,
    "the remotely accepted answer should save");
  created = newAnswerEvents(runtime, knownIds, hotel.id, reservationItem.id);
  assert(scoreCalls === callsBeforeRemote + 1,
    "local incorrect should make exactly one scoring request");
  assert(created.length === 1,
    "remote meaning correction should record exactly one final answer attempt");
  assert(
    created[0].verdict === "near_miss" &&
    created[0].originalVerdict === "incorrect" &&
    created[0].meaningCorrect === true &&
    created[0].scoringSource === "llm",
    "remote result should preserve both the original and final verdicts"
  );
  const remoteProgress = runtime.homeworkProgress(hotel)
    .responses[reservationItem.id];
  assert(
    remoteProgress.status === "near_miss" &&
    remoteProgress.originalVerdict === "incorrect" &&
    remoteProgress.meaningCorrect === true &&
    remoteProgress.scoringSource === "llm" &&
    remoteProgress.modelVersion === "test-model" &&
    remoteProgress.rubricVersion === "hotel-v1",
    "the homework snapshot should contain the final remote grade metadata"
  );

  // A rejected scoring request falls back to the local incorrect grade. It
  // must likewise commit only once, after the rejection is handled.
  runtime.state.homeworkIndex = 3;
  const checkoutItem = items[3].item;
  const fallbackAnswer = "Where is the swimming pool?";
  assert(runtime.homeworkVerdict(checkoutItem, fallbackAnswer) === "incorrect",
    "fallback fixture must fail the local matcher");
  context.fabulitaLearningServices = {
    scoreAnswer() {
      scoreCalls += 1;
      return Promise.reject(new Error("simulated scorer outage"));
    }
  };

  const callsBeforeFallback = scoreCalls;
  knownIds = new Set(runtime.learningEvents().map((event) => event.id));
  assert(await runtime.checkHomeworkAnswerEnhanced(fallbackAnswer) === true,
    "the local fallback answer should still save");
  created = newAnswerEvents(runtime, knownIds, hotel.id, checkoutItem.id);
  assert(scoreCalls === callsBeforeFallback + 1,
    "fallback should attempt the scorer exactly once");
  assert(created.length === 1,
    "scorer rejection should record exactly one final answer attempt");
  assert(
    created[0].verdict === "incorrect" &&
    created[0].originalVerdict === "incorrect" &&
    created[0].meaningCorrect === false &&
    created[0].scoringSource === "local",
    "scorer rejection should persist the local fallback grade"
  );
  const fallbackProgress = runtime.homeworkProgress(hotel)
    .responses[checkoutItem.id];
  assert(
    fallbackProgress.status === "incorrect" &&
    fallbackProgress.scoringSource === "local",
    "the fallback snapshot should identify local scoring"
  );
  assert(runtime.state.homeworkNotice.includes("智能复核暂时不可用"),
    "the learner should be told that local fallback was used");
})().catch((error) => {
  console.error(error && error.stack ? error.stack : error);
  process.exitCode = 1;
});
"""


def _build_my_english(tmp_path):
    project_root = tmp_path / "my-english"
    shutil.copytree(MY_ENGLISH, project_root)
    project = Project(project_root)
    project.save_vocab([])
    vocab.import_file(project, project_root / "vocab.csv")
    page, _, _, _ = build.build(
        project,
        out=tmp_path / "my-english.html",
        include_candidates=False,
        home="index.html",
    )
    return page


def test_my_english_progressive_cloud_scoring_runtime(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the cloud scoring runtime test")

    page = _build_my_english(tmp_path)
    result = subprocess.run(
        [node, "-e", NODE_RUNTIME_TEST, str(page)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        "Node My English cloud-scoring regression failed\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
