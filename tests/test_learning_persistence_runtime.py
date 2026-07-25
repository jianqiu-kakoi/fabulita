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
    window.__learningPersistenceRuntimeTest = {
      state,
      learningPersistence,
      learningEvents,
      appendLearningEvent,
      normalizeLearningEvent,
      learningEventsForExport,
      learningExportEnvelope,
      learningCurrentStateForSync,
      learningHistoryCsv,
      homeworkAssignments,
      homeworkItems,
      homeworkProgress,
      openHomework,
      saveHomeworkAnswer,
      checkHomeworkAnswer,
      deleteHomeworkProgress,
      homeworkStudyWords,
      homeworkStudyProgress,
      openHomeworkStudy,
      recordHomeworkStudyResult,
      rateHomeworkStudy,
      vocabWords,
      reviewAnswerMatches,
      revealReviewAnswer,
      rateReview,
      addQaQuestion,
      qaQuestions
    };
  ` + application.slice(close);

  const storage = new Map();
  const failingSetItemKeys = new Set();
  const localStorage = {
    getItem(key) {
      return storage.has(key) ? storage.get(key) : null;
    },
    setItem(key, value) {
      if (failingSetItemKeys.has(key)) {
        throw new Error("simulated setItem failure for " + key);
      }
      storage.set(key, String(value));
    },
    removeItem(key) {
      storage.delete(key);
    },
    failSetItemFor(key, shouldFail) {
      if (shouldFail) failingSetItemKeys.add(key);
      else failingSetItemKeys.delete(key);
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
    crypto: {
      randomUUID() {
        uuidSequence += 1;
        return "learning-persistence-runtime-" + uuidSequence;
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
  assert(context.__learningPersistenceRuntimeTest,
    "runtime learning-persistence API was not exposed");
  return {
    P,
    runtime: context.__learningPersistenceRuntimeTest,
    localStorage
  };
}

const page = bootPage(process.argv[1]);
const runtime = page.runtime;
const localStorage = page.localStorage;
const HOMEWORK_LS = "fabulita.homework.v1";
const STUDY_LS = "fabulita.homework.study.v1";

assert(runtime.learningPersistence.driver === "browser-local-v1",
  "the current persistence driver should identify itself");
assert(runtime.learningEvents().length === 0,
  "a fresh page should have no unified learning events");
assert(runtime.normalizeLearningEvent({}) === null,
  "malformed learning events must be rejected");

const vocabularyAssignment = runtime.homeworkAssignments.find(
  (candidate) => candidate.id === "ejercicios-vocabulario-a1-1"
);
const conjugationAssignment = runtime.homeworkAssignments.find(
  (candidate) => candidate.id === "ser-estar-conjugation-a1"
);
assert(vocabularyAssignment && conjugationAssignment,
  "both homework assignments are required for isolation coverage");

// Every explicit re-check is an immutable attempt, even if the answer did not change.
runtime.openHomework(vocabularyAssignment);
assert(runtime.saveHomeworkAnswer("lunes").saved === true,
  "the first vocabulary answer should save");
assert(runtime.checkHomeworkAnswer() === true,
  "the first vocabulary answer should be checked");
assert(runtime.checkHomeworkAnswer() === true,
  "checking the unchanged answer again should remain supported");
assert(runtime.saveHomeworkAnswer("sol").saved === true,
  "a replacement vocabulary answer should save");
assert(runtime.checkHomeworkAnswer() === true,
  "the replacement vocabulary answer should be checked");

let vocabularyChecks = runtime.learningEvents().filter((event) =>
  event.source === "homework" &&
  event.action === "answer_checked" &&
  event.assignmentId === vocabularyAssignment.id &&
  event.entityId === "p1-01"
).sort((a, b) => a.attempt - b.attempt);
assert(vocabularyChecks.length === 3,
  "three checks of the same question must append three events");
assert(vocabularyChecks.map((event) => event.attempt).join("|") === "1|2|3",
  "homework attempts should be numbered without overwriting history");
assert(vocabularyChecks.map((event) => event.submittedAnswer).join("|") ===
    "lunes|lunes|sol",
  "every homework event should retain the answer submitted at that check");
assert(vocabularyChecks.map((event) => event.verdict).join("|") ===
    "correct|correct|incorrect",
  "every homework event should retain its historical verdict");
assert(new Set(vocabularyChecks.map((event) => event.id)).size === 3 &&
    new Set(vocabularyChecks.map((event) => event.attemptId)).size === 3,
  "re-check events and their attempts need unique client ids");
assert(vocabularyChecks.every((event) =>
    event.expectedAnswers.includes("lunes") &&
    event.questionType === "single_choice"
  ), "homework history should snapshot the accepted answers and question type");

let vocabularyProgress = runtime.homeworkProgress(vocabularyAssignment);
assert(vocabularyProgress.responses["p1-01"].answer === "sol" &&
    vocabularyProgress.responses["p1-01"].status === "incorrect",
  "the mutable homework snapshot should still contain only the latest state");

// A second assignment shares the project scope but must remain independently addressable.
runtime.openHomework(conjugationAssignment);
assert(runtime.saveHomeworkAnswer("soy").saved === true,
  "the first conjugation answer should save");
assert(runtime.checkHomeworkAnswer() === true,
  "the first conjugation answer should be checked");
let conjugationChecks = runtime.learningEvents().filter((event) =>
  event.source === "homework" &&
  event.action === "answer_checked" &&
  event.assignmentId === conjugationAssignment.id
);
assert(conjugationChecks.length === 1 &&
    conjugationChecks[0].entityId === "ser-01" &&
    conjugationChecks[0].submittedAnswer === "soy" &&
    conjugationChecks[0].verdict === "correct",
  "the conjugation attempt should be isolated by assignment id");
assert(runtime.learningEvents().filter((event) =>
    event.source === "homework" &&
    event.action === "answer_checked" &&
    event.assignmentId === vocabularyAssignment.id
  ).length === 3,
  "checking another assignment must not alter vocabulary history");

// Homework study records the answer/reveal and the later self-rating separately.
runtime.openHomeworkStudy(vocabularyAssignment);
const studyWords = runtime.homeworkStudyWords(vocabularyAssignment);
const lunes = studyWords.find((word) => word.word === "lunes");
const sol = studyWords.find((word) => word.word === "sol");
assert(lunes && sol && runtime.state.homeworkStudyWordId === lunes.id,
  "the fresh study session should begin with lunes");

runtime.state.homeworkStudyAnswer = "Monday";
assert(runtime.recordHomeworkStudyResult("typed") === true,
  "a typed study answer should persist");
let lunesAnswerEvent = runtime.learningEvents().find((event) =>
  event.source === "homework_study" &&
  event.action === "answer_checked" &&
  event.assignmentId === vocabularyAssignment.id &&
  event.entityId === lunes.id
);
assert(lunesAnswerEvent &&
    lunesAnswerEvent.answerMode === "typed" &&
    lunesAnswerEvent.submittedAnswer === "Monday" &&
    lunesAnswerEvent.verdict === "correct" &&
    lunesAnswerEvent.answerCorrect === true,
  "typed study history should retain the raw answer and automatic verdict");
const lunesAttemptId = lunesAnswerEvent.attemptId;
assert(runtime.rateHomeworkStudy("known") === true,
  "the typed study attempt should accept a known rating");
let lunesRatingEvent = runtime.learningEvents().find((event) =>
  event.source === "homework_study" &&
  event.action === "self_rated" &&
  event.assignmentId === vocabularyAssignment.id &&
  event.entityId === lunes.id
);
assert(lunesRatingEvent &&
    lunesRatingEvent.rating === "known" &&
    lunesRatingEvent.attemptId === lunesAttemptId,
  "the self-rating should be an append-only event linked to its answer attempt");

assert(runtime.state.homeworkStudyWordId === sol.id,
  "the second unseen study word should be sol");
runtime.state.homeworkStudyAnswer = "";
assert(runtime.recordHomeworkStudyResult("revealed") === true,
  "directly revealing a study answer should persist");
let solRevealEvent = runtime.learningEvents().find((event) =>
  event.source === "homework_study" &&
  event.action === "answer_revealed" &&
  event.assignmentId === vocabularyAssignment.id &&
  event.entityId === sol.id
);
assert(solRevealEvent &&
    solRevealEvent.answerMode === "revealed" &&
    solRevealEvent.submittedAnswer === "" &&
    solRevealEvent.verdict === "skipped" &&
    solRevealEvent.answerCorrect === null,
  "a reveal event should be distinguishable from a typed wrong answer");
const solAttemptId = solRevealEvent.attemptId;
assert(runtime.rateHomeworkStudy("again") === true,
  "the revealed study attempt should accept an again rating");
let solRatingEvent = runtime.learningEvents().find((event) =>
  event.source === "homework_study" &&
  event.action === "self_rated" &&
  event.assignmentId === vocabularyAssignment.id &&
  event.entityId === sol.id
);
assert(solRatingEvent &&
    solRatingEvent.rating === "again" &&
    solRatingEvent.attemptId === solAttemptId,
  "the reveal rating should link back to the reveal attempt");
assert(runtime.learningEvents().filter((event) =>
    event.source === "homework_study" &&
    event.assignmentId === vocabularyAssignment.id
  ).length === 4,
  "typed plus rating and reveal plus rating should create four study events");

let studyProgress = runtime.homeworkStudyProgress(vocabularyAssignment);
assert(studyProgress.responses[lunes.id].mode === "typed" &&
    studyProgress.responses[lunes.id].rating === "known" &&
    studyProgress.responses[sol.id].mode === "revealed" &&
    studyProgress.responses[sol.id].rating === "again",
  "the latest study snapshots should remain available alongside event history");

// Review contributes typed/revealed answer events and terminal rating events.
const bien = runtime.vocabWords.find((word) => word.w === "bien");
const con = runtime.vocabWords.find((word) => word.w === "con");
assert(bien && con, "review fixtures should contain bien and con");

Object.assign(runtime.state, {
  reviewQueue: [bien],
  reviewTotal: 1,
  reviewSessionDone: 0,
  reviewSessionId: "rs:learning-persistence-typed",
  reviewRevealed: false,
  reviewAnswer: "good",
  reviewAnswerCorrect: runtime.reviewAnswerMatches(bien, "good"),
  reviewCardStartedAt: Date.now() - 25
});
runtime.revealReviewAnswer("typed", "typed_submit");
runtime.rateReview("known", "button");

Object.assign(runtime.state, {
  reviewQueue: [con],
  reviewTotal: 1,
  reviewSessionDone: 0,
  reviewSessionId: "rs:learning-persistence-skipped",
  reviewRevealed: false,
  reviewAnswer: "",
  reviewAnswerCorrect: null,
  reviewCardStartedAt: Date.now() - 25
});
runtime.revealReviewAnswer("skipped", "manual_button");
runtime.rateReview("again", "button");

let reviewLearningEvents = runtime.learningEvents().filter((event) =>
  event.source === "review"
);
assert(reviewLearningEvents.length === 4,
  "typed/skipped answers and their ratings should create four review events");
assert(reviewLearningEvents.some((event) =>
    event.action === "answer_checked" &&
    event.entityId === "w:bien" &&
    event.submittedAnswer === "good" &&
    event.verdict === "correct"
  ), "typed review input should be retained");
assert(reviewLearningEvents.some((event) =>
    event.action === "answer_revealed" &&
    event.entityId === "w:con" &&
    event.answerMode === "skipped" &&
    event.verdict === "skipped"
  ), "skipped review input should be retained");
assert(reviewLearningEvents.some((event) =>
    event.action === "self_rated" &&
    event.entityId === "w:bien" &&
    event.rating === "known"
  ) && reviewLearningEvents.some((event) =>
    event.action === "self_rated" &&
    event.entityId === "w:con" &&
    event.rating === "again"
  ), "review ratings should stay separate from automatic answer verdicts");
assert(runtime.learningEventsForExport().filter((event) =>
    event.source === "review"
  ).length === 4,
  "legacy review events must not duplicate their linked unified rating events");

// A real Q&A snapshot supplies a formula-like value for CSV injection coverage.
assert(runtime.addQaQuestion("=2+3") === true,
  "a Q&A question should persist through the same storage gateway");
assert(runtime.qaQuestions().length === 1,
  "the Q&A snapshot should be readable");
assert(runtime.learningEvents().some((event) =>
    event.source === "qa" &&
    event.action === "question_created" &&
    event.prompt === "=2+3"
  ), "Q&A creation should contribute its source to the unified event stream");

// Reset removes only the selected mutable snapshot; append-only attempts survive.
const eventsBeforeReset = runtime.learningEvents().length;
assert(runtime.deleteHomeworkProgress(vocabularyAssignment) === true,
  "resetting the vocabulary assignment should succeed");
assert(runtime.learningEvents().length === eventsBeforeReset + 1,
  "reset should append its own audit event");
assert(runtime.learningEvents().filter((event) =>
    event.source === "homework" &&
    event.action === "answer_checked" &&
    event.assignmentId === vocabularyAssignment.id
  ).length === 3,
  "reset must preserve all historical vocabulary checks");
assert(runtime.learningEvents().some((event) =>
    event.source === "homework" &&
    event.action === "assignment_reset" &&
    event.assignmentId === vocabularyAssignment.id
  ), "reset should be represented explicitly in the audit stream");
vocabularyProgress = runtime.homeworkProgress(vocabularyAssignment);
assert(Object.keys(vocabularyProgress.responses).length === 0,
  "the selected assignment snapshot should be cleared");
const conjugationProgress = runtime.homeworkProgress(conjugationAssignment);
assert(conjugationProgress.responses["ser-01"].answer === "soy" &&
    conjugationProgress.responses["ser-01"].status === "correct",
  "resetting one assignment must preserve the other assignment snapshot");
studyProgress = runtime.homeworkStudyProgress(vocabularyAssignment);
assert(studyProgress.responses[lunes.id].rating === "known" &&
    studyProgress.responses[sol.id].rating === "again",
  "resetting exercise answers must preserve study snapshots");

// The generic append/normalize API is idempotent by client event id.
let normalized = runtime.normalizeLearningEvent(runtime.learningEvents()[0]);
assert(normalized && normalized.schema === "fabulita.learning-event.v1",
  "a stored event should survive normalization");
const countBeforeDuplicate = runtime.learningEvents().length;
assert(runtime.appendLearningEvent(normalized) === true,
  "re-appending an existing client event should be a safe success");
assert(runtime.learningEvents().length === countBeforeDuplicate,
  "the persistence outbox must deduplicate the same client event id");
assert(runtime.learningPersistence.listEvents().length === countBeforeDuplicate,
  "the public persistence interface should expose the same event list");

const exportEvents = runtime.learningEventsForExport();
const envelope = runtime.learningExportEnvelope();
assert(envelope.schema === "fabulita.learning-export.v1",
  "AI export should use the unified learning schema");
assert(envelope.persistence.driver === "browser-local-v1" &&
    envelope.persistence.localAuditKey === "fabulita.learning.events.v1" &&
    envelope.persistence.localOutboxKey === "fabulita.learning.sync.v1",
  "the export should describe its current persistence backend");
const syncRoot = JSON.parse(
  localStorage.getItem("fabulita.learning.sync.v1")
);
const syncScope = syncRoot.scopes[envelope.project.scope];
assert(syncScope.migrationVersion === 1 &&
    syncScope.events.length === exportEvents.length,
  "every local audit event should enter the durable sync outbox exactly once");
assert(syncScope.acknowledgedEventIds.length === 0,
  "an offline page must not mark outbox events as remotely acknowledged");
const cloudCurrentState = runtime.learningCurrentStateForSync(
  envelope.currentState
);
assert(envelope.currentState.rawScopes.reviewEvents &&
    !Object.prototype.hasOwnProperty.call(
      cloudCurrentState.rawScopes, "reviewEvents"
    ),
  "cloud state must omit append-only legacy review history without deleting it locally");
assert(envelope.events.length === exportEvents.length &&
    envelope.summary.total === exportEvents.length,
  "the export summary and event payload should agree");
assert(envelope.summary.bySource.homework === 5 &&
    envelope.summary.bySource.homework_study === 4 &&
    envelope.summary.bySource.review === 4 &&
    envelope.summary.bySource.qa === 1,
  "the export should include every persisted learning source without duplication");
assert(new Set(envelope.events.map((event) => event.source)).size === 4,
  "all four source kinds should be represented in the event payload");

const exportedVocabulary = envelope.currentState.homework.find(
  (assignment) => assignment.assignmentId === vocabularyAssignment.id
);
const exportedConjugation = envelope.currentState.homework.find(
  (assignment) => assignment.assignmentId === conjugationAssignment.id
);
assert(exportedVocabulary && exportedConjugation,
  "the export should include snapshots for both assignments");
assert(exportedVocabulary.items.every((item) => item.response === null),
  "the reset vocabulary snapshot should be honestly represented as empty");
assert(exportedVocabulary.study.words.find((word) =>
    word.wordId === lunes.id
  ).response.rating === "known" &&
    exportedVocabulary.study.words.find((word) =>
      word.wordId === sol.id
    ).response.rating === "again",
  "homework study snapshots should be included in the export");
assert(exportedConjugation.items.find((item) =>
    item.itemId === "ser-01"
  ).response.answer === "soy",
  "the other assignment's latest answer should remain in the export");
assert(envelope.currentState.reviewCards.some((card) =>
    card.word === "bien" && card.reviews === 1
  ) && envelope.currentState.reviewCards.some((card) =>
    card.word === "con" && card.reviews === 1
  ), "current review scheduling snapshots should be included");
assert(envelope.currentState.qa.length === 1 &&
    envelope.currentState.qa[0].question === "=2+3",
  "the current Q&A snapshot should be included");
assert(envelope.completeness.preexistingHomeworkSnapshotsIncluded === true &&
    envelope.completeness.preexistingHomeworkAttemptDetailsRecoverable === false,
  "the export should state the historical boundary explicitly");
assert(runtime.learningPersistence.exportAll().schema === envelope.schema,
  "the persistence interface should expose the unified export");

const csv = runtime.learningHistoryCsv(exportEvents);
assert(csv.startsWith("\uFEFF\"event_id\",\"occurred_at\",\"source\",\"action\""),
  "CSV should include a BOM and unified event columns");
assert(csv.includes("\"assignment_id\"") &&
    csv.includes("\"submitted_answer\"") &&
    csv.includes("\"expected_answers\"") &&
    csv.includes("\"snapshot_persisted\""),
  "CSV should expose fields needed for downstream analysis");
assert(csv.includes("\"'=2+3\""),
  "formula-like values must be prefixed so spreadsheet software treats them as text");
assert(csv.includes("\"Monday\"") &&
    csv.includes("\"lunes\"") &&
    csv.includes("\"soy\""),
  "CSV should retain raw answers and accepted-answer snapshots");
const csvRows = csv.trim().split(/\r?\n/);
assert(csvRows.length === exportEvents.length + 1,
  "CSV should contain exactly one row per exported event");

// If only the mutable homework snapshot write fails, the immutable event must
// still describe the answer submitted in this call rather than re-reading the
// previously persisted answer.
runtime.openHomework(vocabularyAssignment);
assert(runtime.saveHomeworkAnswer("lunes").saved === true,
  "the failure fixture should persist an older homework draft first");
const failureEventIdsBefore = new Set(runtime.learningEvents().map((event) => event.id));
localStorage.failSetItemFor(HOMEWORK_LS, true);
assert(runtime.saveHomeworkAnswer("sol").saved === false,
  "the replacement draft should report the simulated snapshot failure");
assert(runtime.checkHomeworkAnswer("sol") === false,
  "checking should report that its mutable snapshot could not be saved");
localStorage.failSetItemFor(HOMEWORK_LS, false);
const failureEvents = runtime.learningEvents().filter((event) =>
  !failureEventIdsBefore.has(event.id) &&
  event.source === "homework" &&
  event.action === "answer_checked" &&
  event.assignmentId === vocabularyAssignment.id &&
  event.entityId === "p1-01"
);
assert(failureEvents.length === 1,
  "the failed snapshot write should still append exactly one answer event");

// Raw V1 records may outlive a renamed/deleted assignment item or study word.
// They must remain present in AI export even though the current content model
// cannot map them into its cleaned item/word lists.
const rawHomeworkRoot = JSON.parse(localStorage.getItem(HOMEWORK_LS));
const rawHomeworkScope = rawHomeworkRoot.scopes[Object.keys(rawHomeworkRoot.scopes)[0]];
rawHomeworkScope.assignments[vocabularyAssignment.id].responses["orphan-item-v0"] = {
  answer: "legacy orphan answer",
  status: "incorrect",
  checkedAt: 123456,
  updatedAt: 123456
};
rawHomeworkScope.assignments["removed-assignment-v0"] = {
  responses: {
    "removed-question-v0": {
      answer: "answer from removed assignment",
      status: "correct",
      checkedAt: 123457,
      updatedAt: 123457
    }
  },
  currentItemId: "removed-question-v0",
  completedAt: null,
  updatedAt: 123457
};
localStorage.setItem(HOMEWORK_LS, JSON.stringify(rawHomeworkRoot));

const rawStudyRoot = JSON.parse(localStorage.getItem(STUDY_LS));
const rawStudyScope = rawStudyRoot.scopes[Object.keys(rawStudyRoot.scopes)[0]];
rawStudyScope.assignments[vocabularyAssignment.id].responses["orphan-word-v0"] = {
  answer: "legacy orphan meaning",
  attempts: 1,
  correctCount: 0,
  answerCorrect: false,
  answerVerdict: "incorrect",
  mode: "typed",
  rating: "again",
  checkedAt: 123458,
  studiedAt: 123458,
  ratedAt: 123459,
  updatedAt: 123459
};
rawStudyScope.assignments["removed-study-assignment-v0"] = {
  responses: {
    "removed-word-v0": {
      answer: "meaning from removed study assignment",
      attempts: 1,
      correctCount: 1,
      answerCorrect: true,
      answerVerdict: "correct",
      mode: "typed",
      rating: "known",
      checkedAt: 123460,
      studiedAt: 123460,
      ratedAt: 123461,
      updatedAt: 123461
    }
  },
  currentWordId: "removed-word-v0",
  completedAt: null,
  updatedAt: 123461
};
localStorage.setItem(STUDY_LS, JSON.stringify(rawStudyRoot));

const orphanExportJson = JSON.stringify(runtime.learningExportEnvelope());
[
  "orphan-item-v0",
  "legacy orphan answer",
  "removed-assignment-v0",
  "removed-question-v0",
  "answer from removed assignment",
  "orphan-word-v0",
  "legacy orphan meaning",
  "removed-study-assignment-v0",
  "removed-word-v0",
  "meaning from removed study assignment"
].forEach((expected) => {
  assert(orphanExportJson.includes(expected),
    "raw orphan snapshots should retain " + expected);
});

assert(failureEvents[0].submittedAnswer === "sol" &&
    failureEvents[0].verdict === "incorrect" &&
    failureEvents[0].snapshotPersisted === false,
  "the fallback event must use this submission and mark only its snapshot as unpersisted");
assert(runtime.homeworkProgress(vocabularyAssignment).responses["p1-01"].answer === "lunes",
  "the failed mutable write should leave the older stored snapshot untouched");

assert(envelope.summary.byVerdict.correct === 5 &&
    envelope.summary.byVerdict.incorrect === 1 &&
    envelope.summary.byVerdict.skipped === 2 &&
    Object.values(envelope.summary.byVerdict).reduce(
      (total, count) => total + count, 0
    ) === 8,
  "answer verdict totals must count only answer_checked/answer_revealed, not self_rated copies");
"""


def test_learning_persistence_events_snapshots_and_export(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the inline learning persistence test")

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
        "Node learning persistence regression failed\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
