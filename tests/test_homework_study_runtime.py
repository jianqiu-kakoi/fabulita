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

function occurrences(text, needle) {
  return text.split(needle).length - 1;
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
    window.__homeworkStudyRuntimeTest = {
      state,
      homeworkAssignments,
      homeworkStudyWords,
      homeworkStudyWordByText,
      homeworkStudyAnswerMatches,
      homeworkStudyAnswerVerdict,
      homeworkStudyNearMissSuggestion,
      homeworkStudyProgress,
      homeworkStudyStats,
      openHomeworkStudy,
      recordHomeworkStudyResult,
      rateHomeworkStudy,
      homeworkOptionMeaningRows,
      homeworkAnswerVocabulary,
      homeworkAnswerVocabularyHtml,
      homeworkResolvedSentence,
      homeworkSentenceSegments,
      toggleHomeworkSentenceWord,
      homeworkSentenceFeedbackHtml,
      dashboardHomeworkListHtml,
      dashboardHomeworkStudyRowsHtml,
      dashboardHomeworkStudyCardHtml,
      dashboardHomeworkQuestionHtml,
      openHomework,
      saveHomeworkAnswer,
      checkHomeworkAnswer,
      deleteHomeworkProgress
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
    crypto: { randomUUID: () => "homework-study-runtime-uuid" },
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
  assert(context.__homeworkStudyRuntimeTest, "runtime test API was not exposed");
  return {
    P,
    runtime: context.__homeworkStudyRuntimeTest,
    localStorage,
    app
  };
}

const page = bootPage(process.argv[1]);
const runtime = page.runtime;
const localStorage = page.localStorage;
const HOMEWORK_LS = "fabulita.homework.v1";
const STUDY_LS = "fabulita.homework.study.v1";
const REVIEW_LS = "fabulita.review.v1";
const EVENTS_LS = "fabulita.review.events.v1";
const QA_LS = "fabulita.qa.v1";

const assignment = runtime.homeworkAssignments.find(
  (candidate) => candidate.id === "ejercicios-vocabulario-a1-1"
);
assert(assignment, "expected the A1 vocabulary homework assignment");
const studyWords = runtime.homeworkStudyWords(assignment);
assert(studyWords.length === 93, "expected 93 homework study words");

const lunes = runtime.homeworkStudyWordByText(assignment, " LUNES. ");
const sol = runtime.homeworkStudyWordByText(assignment, "sol");
const frio = runtime.homeworkStudyWordByText(assignment, "frío");
const cafe = runtime.homeworkStudyWordByText(assignment, "café");
assert(lunes && sol && frio && cafe,
  "the first question choices and cafe must resolve to study words");
assert(runtime.homeworkStudyAnswerMatches(lunes, "星期一") === true,
  "lunes should accept its Chinese meaning");
assert(runtime.homeworkStudyAnswerMatches(lunes, "周一") === true,
  "lunes should accept its Chinese alias");
assert(runtime.homeworkStudyAnswerMatches(lunes, "Monday") === true,
  "lunes should accept its English meaning");
assert(runtime.homeworkStudyAnswerMatches(lunes, "星期一 / Monday") === true,
  "lunes should accept a slash-separated bilingual answer");
assert(runtime.homeworkStudyAnswerMatches(lunes, "sun") === false,
  "lunes must reject an unrelated meaning");
assert(runtime.homeworkStudyAnswerMatches(sol, "sunshine") === true,
  "sol should accept its English alias");
assert(runtime.homeworkStudyAnswerMatches(frio, "冷") === true,
  "frío should accept its short Chinese meaning");
assert(runtime.homeworkStudyAnswerMatches(frio, "cold") === true,
  "frío should accept its English meaning");
assert(runtime.homeworkStudyAnswerVerdict(cafe, "coffee") === "correct",
  "coffee should remain an exact accepted English meaning for café");
assert(runtime.homeworkStudyAnswerVerdict(cafe, "caffee") === "near_miss",
  "caffee should be treated as a spelling near miss for coffee");
assert(runtime.homeworkStudyNearMissSuggestion(cafe, "caffee") === "coffee",
  "the near miss should suggest the intended English spelling");
assert(runtime.homeworkStudyAnswerMatches(cafe, "caffee") === false,
  "a near miss must not be promoted to a correct answer");
assert(runtime.homeworkStudyAnswerVerdict(cafe, "and") === "incorrect",
  "an unrelated English word must remain incorrect");

const practicaAssignment = runtime.homeworkAssignments.find(
  (candidate) => candidate.id === "practica-ser-estar-vocabulario-a0"
);
const esta = practicaAssignment &&
  runtime.homeworkStudyWordByText(practicaAssignment, "está");
assert(esta, "the A0 practice should expose está as a study word");
assert(runtime.homeworkStudyAnswerMatches(esta, "他在") === true,
  "está should accept the natural Chinese gloss 他在");
assert(runtime.homeworkStudyAnswerMatches(esta, "她在") === true &&
    runtime.homeworkStudyAnswerMatches(esta, "它在") === true,
  "está should accept feminine and inanimate Chinese subject variants");
assert(runtime.homeworkStudyAnswerVerdict(esta, "他在") === "correct",
  "the visible study scorer should grade 他在 as correct for está");

const listHtml = runtime.dashboardHomeworkListHtml();
assert(listHtml.includes('data-homework-study-open="' + assignment.id + '"'),
  "the homework card should link to the study module");
assert(listHtml.includes("先学单词"), "a fresh homework should invite study first");
assert(listHtml.includes("0 / 93 单词已学习"), "the homework card should show study progress");
const studyRowsHtml = runtime.dashboardHomeworkStudyRowsHtml(assignment);
assert(occurrences(studyRowsHtml, 'data-homework-study-word="') === 93,
  "the study table should render all 93 words");
assert(studyRowsHtml.includes("星期一、周一") && studyRowsHtml.includes("Monday"),
  "the study table should show Chinese and English meanings");
assert(studyRowsHtml.includes("第一天") && studyRowsHtml.includes("first day"),
  "the study table should include prompt-reading helpers");

runtime.openHomework(assignment);
const firstItem = assignment.sections[0].items[0];
assert(runtime.homeworkResolvedSentence(
  firstItem, { answer: "lunes" }
) === null, "a saved but unchecked draft must not resolve a sentence");
assert(runtime.homeworkSentenceFeedbackHtml(
  assignment, firstItem, { answer: "lunes" }
) === "", "sentence feedback must stay hidden before grading");
const ungradedRows = runtime.homeworkOptionMeaningRows(
  assignment, firstItem, { answer: "lunes" }
);
assert(ungradedRows.length === 0, "choice meanings must stay hidden before grading");
const ungradedHtml = runtime.dashboardHomeworkQuestionHtml(assignment);
assert(!ungradedHtml.includes("三个选项的意思"),
  "the first question must not reveal the option glossary before grading");
assert(!ungradedHtml.includes("星期一、周一") &&
    !ungradedHtml.includes("太阳；阳光") &&
    !ungradedHtml.includes("寒冷；冷的"),
  "none of the three choice meanings should leak before grading");
assert(!ungradedHtml.includes("homework-sentence-result") &&
    !ungradedHtml.includes("星期一是一周的第一天。") &&
    !ungradedHtml.includes("data-homework-sentence-word"),
  "the completed sentence, translation, and word buttons must not leak before grading");

assert(runtime.saveHomeworkAnswer("lunes").saved === true,
  "the correct first answer should save");
assert(runtime.checkHomeworkAnswer() === true,
  "the correct first answer should be gradable");
const resolvedFirst = runtime.homeworkResolvedSentence(
  firstItem, { answer: "lunes", status: "correct" }
);
assert(resolvedFirst &&
    resolvedFirst.answer === "lunes" &&
    resolvedFirst.target === "El lunes es el primer día de la semana." &&
    resolvedFirst.translation === "星期一是一周的第一天。",
  "a correct answer should resolve the completed target-language sentence and Chinese translation");
const firstSegments = runtime.homeworkSentenceSegments(
  assignment, resolvedFirst.target
);
assert(firstSegments.map((segment) => segment.text).join("") === resolvedFirst.target,
  "sentence segments must reconstruct the source sentence byte for byte");
const firstDaySegments = firstSegments.filter(
  (segment) => segment.word && segment.text.toLowerCase() === "primer día"
);
assert(firstDaySegments.length === 1 &&
    firstDaySegments[0].wordId === "hw-c-primer-dia",
  "primer día must use the longest phrase match instead of splitting the phrase");
assert(firstSegments.some((segment) =>
    segment.text.toLowerCase() === "lunes" && segment.wordId === lunes.id
  ), "the filled answer should be an expandable sentence word");
assert(firstSegments.some((segment) =>
    segment.text.toLowerCase() === "semana" && segment.wordId === "hw-c-semana"
  ), "the context word semana should be expandable");
assert(firstSegments.some((segment) =>
    segment.text.toLowerCase() === "es" && segment.wordId === "hw-s-ser"
  ), "sentenceLexicon forms should resolve conjugated helper words");
const correctRows = runtime.homeworkOptionMeaningRows(
  assignment, firstItem, { answer: "lunes", status: "correct" }
);
assert(correctRows.length === 3, "grading should return all three option meanings");
assert(correctRows[0].option === "lunes" &&
    correctRows[0].gloss === "星期一、周一" &&
    correctRows[0].english === "Monday" &&
    correctRows[0].selected === true &&
    correctRows[0].accepted === true,
  "lunes should be marked as both selected and accepted");
assert(correctRows[1].option === "sol" &&
    correctRows[1].gloss === "太阳；阳光" &&
    correctRows[1].english === "sun; sunshine" &&
    correctRows[1].selected === false &&
    correctRows[1].accepted === false,
  "sol should retain its full bilingual meaning");
assert(correctRows[2].option === "frío" &&
    correctRows[2].gloss === "寒冷；冷的" &&
    correctRows[2].english === "cold" &&
    correctRows[2].selected === false &&
    correctRows[2].accepted === false,
  "frío should retain its full bilingual meaning");
let gradedHtml = runtime.dashboardHomeworkQuestionHtml(assignment);
const gradedText = gradedHtml.replace(/<[^>]*>/g, "");
assert(gradedHtml.includes("homework-sentence-result") &&
    gradedText.includes("El lunes es el primer día de la semana.") &&
    gradedText.includes("星期一是一周的第一天。"),
  "a correct grade should render the completed sentence and its translation");
assert(gradedHtml.includes("三个选项的意思") &&
    gradedHtml.includes("星期一、周一") && gradedHtml.includes("Monday") &&
    gradedHtml.includes("太阳；阳光") && gradedHtml.includes("sun; sunshine") &&
    gradedHtml.includes("寒冷；冷的") && gradedHtml.includes("cold"),
  "a correct grade should render all three bilingual meanings");
assert(occurrences(gradedHtml, "你的选择") === 1,
  "exactly one option should be tagged as the learner's choice");
assert(occurrences(gradedHtml, "可接受答案") === 1,
  "the first question should have one accepted option tag");

const sentenceStorageKeys = [HOMEWORK_LS, STUDY_LS, REVIEW_LS, EVENTS_LS, QA_LS];
const sentenceStorageBefore = JSON.stringify(
  sentenceStorageKeys.map((key) => localStorage.getItem(key))
);
assert(runtime.toggleHomeworkSentenceWord(assignment, lunes.id) === true,
  "a mapped word in the completed sentence should expand");
let sentenceHtml = runtime.homeworkSentenceFeedbackHtml(
  assignment, firstItem, { answer: "lunes", status: "correct" }
);
assert(sentenceHtml.includes('data-homework-sentence-word="' + lunes.id + '"') &&
    sentenceHtml.includes('aria-expanded="true"') &&
    sentenceHtml.includes("星期一、周一") &&
    sentenceHtml.includes("Monday"),
  "expanding lunes should reveal its Chinese and English meanings");
assert(runtime.toggleHomeworkSentenceWord(assignment, "not-in-this-sentence") === false,
  "an unknown or unavailable sentence word must not expand");
assert(runtime.toggleHomeworkSentenceWord(assignment, lunes.id) === true &&
    runtime.state.homeworkSentenceWordId === "",
  "clicking the active word again should collapse its definition");
const sentenceStorageAfter = JSON.stringify(
  sentenceStorageKeys.map((key) => localStorage.getItem(key))
);
assert(sentenceStorageAfter === sentenceStorageBefore,
  "expanding or collapsing a sentence word must not write any localStorage");

assert(runtime.saveHomeworkAnswer("sol").saved === true,
  "an incorrect replacement choice should save");
assert(runtime.checkHomeworkAnswer() === true,
  "the incorrect replacement choice should still be graded");
gradedHtml = runtime.dashboardHomeworkQuestionHtml(assignment);
assert(gradedHtml.includes("暂时不对") &&
    gradedHtml.includes("星期一、周一") &&
    gradedHtml.includes("太阳；阳光") &&
    gradedHtml.includes("寒冷；冷的"),
  "an incorrect grade should still show all three meanings");
assert(!gradedHtml.includes("homework-sentence-result") &&
    !gradedHtml.includes("星期一是一周的第一天。") &&
    runtime.homeworkResolvedSentence(
      firstItem, { answer: "sol", status: "incorrect" }
    ) === null,
  "an incorrect answer must not display a completed sentence");
const wrongRows = runtime.homeworkOptionMeaningRows(
  assignment, firstItem, { answer: "sol", status: "incorrect" }
);
assert(wrongRows.find((row) => row.option === "sol").selected === true,
  "the incorrect option should still be tagged as selected");
assert(wrongRows.find((row) => row.option === "lunes").accepted === true,
  "the accepted option should remain identified after an error");

assert(runtime.saveHomeworkAnswer("lunes").saved === true,
  "the first answer should be restorable");
assert(runtime.checkHomeworkAnswer() === true,
  "the restored correct answer should be gradable");
const homeworkBeforeStudy = localStorage.getItem(HOMEWORK_LS);
assert(homeworkBeforeStudy && runtime.dashboardHomeworkQuestionHtml(assignment).includes("1 / 50"),
  "the fixture should have one of fifty homework answers checked");

localStorage.setItem(REVIEW_LS, '{"sentinel":"review"}');
localStorage.setItem(EVENTS_LS, '{"sentinel":"events"}');
localStorage.setItem(QA_LS, '{"sentinel":"qa"}');
const reviewBeforeStudy = localStorage.getItem(REVIEW_LS);
const eventsBeforeStudy = localStorage.getItem(EVENTS_LS);
const qaBeforeStudy = localStorage.getItem(QA_LS);

runtime.openHomeworkStudy(assignment);
assert(runtime.state.homeworkStudyOpen === true,
  "opening study should switch the homework into study mode");
assert(runtime.state.homeworkStudyWordId === lunes.id,
  "a fresh study session should begin with lunes");
let studyCardHtml = runtime.dashboardHomeworkStudyCardHtml(assignment);
assert(studyCardHtml.includes("填写中文或英文意思"),
  "the study card should accept a typed bilingual meaning");

runtime.state.homeworkStudyAnswer = "Monday";
assert(runtime.recordHomeworkStudyResult("typed") === true,
  "a typed study answer should save");
assert(runtime.state.homeworkStudyAnswerCorrect === true,
  "Monday should be scored correct for lunes");
studyCardHtml = runtime.dashboardHomeworkStudyCardHtml(assignment);
assert(studyCardHtml.includes("答对了") &&
    studyCardHtml.includes("星期一、周一") &&
    studyCardHtml.includes("Monday"),
  "a checked study card should reveal its bilingual definition");
assert(runtime.rateHomeworkStudy("known") === true,
  "a revealed study word should accept the known rating");

assert(runtime.state.homeworkStudyWordId === sol.id,
  "the next unseen study word should be sol");
runtime.state.homeworkStudyAnswer = "Monday";
assert(runtime.recordHomeworkStudyResult("typed") === true,
  "an incorrect typed study answer should still persist");
assert(runtime.state.homeworkStudyAnswerCorrect === false,
  "Monday should be incorrect for sol");
studyCardHtml = runtime.dashboardHomeworkStudyCardHtml(assignment);
assert(studyCardHtml.includes("暂时不对") &&
    studyCardHtml.includes("太阳；阳光") &&
    studyCardHtml.includes("sun; sunshine"),
  "an incorrect study result should reveal the target definition");
assert(runtime.rateHomeworkStudy("again") === true,
  "a revealed study word should accept the revisit rating");

const studyProgress = runtime.homeworkStudyProgress(assignment);
const studyStats = runtime.homeworkStudyStats(assignment, studyProgress);
assert(studyStats.total === 93 && studyStats.studied === 2 &&
    studyStats.correct === 1 && studyStats.revisit === 1,
  "study stats should separate learned, correct, and revisit counts");
assert(studyProgress.responses[lunes.id].rating === "known",
  "the known rating should persist");
assert(studyProgress.responses[sol.id].rating === "again",
  "the revisit rating should persist");
assert(localStorage.getItem(STUDY_LS),
  "study activity should use its own localStorage record");
assert(localStorage.getItem(HOMEWORK_LS) === homeworkBeforeStudy,
  "study activity must not alter homework answers");
assert(localStorage.getItem(REVIEW_LS) === reviewBeforeStudy,
  "study activity must not alter review scheduling");
assert(localStorage.getItem(EVENTS_LS) === eventsBeforeStudy,
  "study activity must not append review events");
assert(localStorage.getItem(QA_LS) === qaBeforeStudy,
  "study activity must not alter Q&A");

runtime.openHomework(assignment);
assert(runtime.state.homeworkStudyOpen === false,
  "entering the exercise should leave study mode");
assert(runtime.state.homeworkIndex === 0,
  "entering the exercise should restore the saved current question");
const restoredHomeworkHtml = runtime.dashboardHomeworkQuestionHtml(assignment);
assert(restoredHomeworkHtml.includes("1 / 50") &&
    restoredHomeworkHtml.includes('value="lunes" checked'),
  "entering the exercise should restore the existing one-of-fifty answer");

const multiItem = assignment.sections[0].items[6];
const multiResolved = runtime.homeworkResolvedSentence(
  multiItem, { answer: "leche", status: "correct" }
);
assert(multiResolved &&
    multiResolved.target === "Me gusta beber leche cuando tengo sed." &&
    multiResolved.translation === "我口渴时喜欢喝牛奶。",
  "an accepted alternative must use its own filled sentence and translation");
const multiRows = runtime.homeworkOptionMeaningRows(
  assignment, multiItem, { answer: "leche", status: "correct" }
);
assert(multiRows.length === 3, "the multi-answer item should expose all options");
assert(multiRows.filter((row) => row.accepted).map((row) => row.option).join("|") === "agua|leche",
  "both reasonable answers should be tagged as accepted");
assert(multiRows.filter((row) => row.selected).map((row) => row.option).join("|") === "leche",
  "only the learner's actual choice should be tagged as selected");

runtime.state.homeworkIndex = 6;
assert(runtime.saveHomeworkAnswer("leche").saved === true,
  "the accepted alternative should save");
assert(runtime.checkHomeworkAnswer() === true,
  "the accepted alternative should grade as correct");
const multiHtml = runtime.dashboardHomeworkQuestionHtml(assignment);
assert(occurrences(multiHtml, "可接受答案") === 2,
  "the rendered feedback should show both accepted-answer tags");
assert(occurrences(multiHtml, "你的选择") === 1,
  "the rendered feedback should show one selected-answer tag");
assert(multiHtml.replace(/<[^>]*>/g, "").includes(
    "Me gusta beber leche cuando tengo sed."
  ) && multiHtml.includes("我口渴时喜欢喝牛奶。"),
  "the rendered multi-answer feedback should follow the selected accepted answer");

const partTwoItem = assignment.sections[1].items[0];
assert(runtime.homeworkResolvedSentence(
  partTwoItem, { answer: "martes", status: "correct" }
) === null, "a Part 2 translation prompt must not fabricate a completed sentence");
assert(runtime.homeworkSentenceFeedbackHtml(
  assignment, partTwoItem, { answer: "martes", status: "correct" }
) === "", "Part 2 must not render the sentence feedback module");
const partTwoVocabulary = runtime.homeworkAnswerVocabulary(
  assignment, partTwoItem, { answer: "martes", status: "correct" }
);
assert(partTwoVocabulary &&
    partTwoVocabulary.word === "martes" &&
    partTwoVocabulary.gloss.includes("星期二") &&
    partTwoVocabulary.gloss.includes("周二") &&
    partTwoVocabulary.english === "Tuesday",
  "a correct Part 2 translation should resolve its Spanish, Chinese, and English vocabulary");
const partTwoVocabularyHtml = runtime.homeworkAnswerVocabularyHtml(
  assignment, partTwoItem, { answer: "martes", status: "correct" }
);
assert(partTwoVocabularyHtml.includes(">martes<") &&
    partTwoVocabularyHtml.includes("星期二") &&
    partTwoVocabularyHtml.includes("周二") &&
    partTwoVocabularyHtml.includes(">Tuesday<") &&
    partTwoVocabularyHtml.includes('data-homework-answer-speak="martes"'),
  "a correct Part 2 translation should render the answer word, meanings, and pronunciation control");
assert(runtime.homeworkAnswerVocabularyHtml(
  assignment, partTwoItem, { answer: "lunes", status: "incorrect" }
) === "", "an incorrect Part 2 translation must not reveal the answer vocabulary");

runtime.state.homeworkIndex = assignment.sections[0].items.length;
assert(runtime.saveHomeworkAnswer("martes").saved === true,
  "the Tuesday translation should save before grading");
assert(runtime.checkHomeworkAnswer() === true,
  "martes should be graded as the correct translation of Tuesday");
const partTwoHtml = runtime.dashboardHomeworkQuestionHtml(assignment);
assert(partTwoHtml.includes("homework-answer-vocabulary") &&
    partTwoHtml.includes('data-homework-answer-speak="martes"'),
  "the graded homework page should include the answer vocabulary card");

const openWindowItem = assignment.sections[0].items[12];
const openWindowResolved = runtime.homeworkResolvedSentence(
  openWindowItem, { answer: "ventana", status: "correct" }
);
assert(openWindowResolved &&
    openWindowResolved.target === "La ventana está abierta.",
  "the open-window fixture should resolve its completed sentence");
const openWindowSegments = runtime.homeworkSentenceSegments(
  assignment, openWindowResolved.target
);
const abiertaSegment = openWindowSegments.find(
  (segment) => segment.text.toLowerCase() === "abierta"
);
assert(abiertaSegment &&
    abiertaSegment.word &&
    abiertaSegment.word.word === "abierto / abierta",
  "slash-separated study-word forms must resolve the surface form abierta");

const studyBeforeReset = localStorage.getItem(STUDY_LS);
assert(runtime.deleteHomeworkProgress(assignment) === true,
  "reset should remove the exercise progress");
assert(localStorage.getItem(STUDY_LS) === studyBeforeReset,
  "resetting homework answers must preserve study progress");
const studyAfterReset = runtime.homeworkStudyStats(
  assignment, runtime.homeworkStudyProgress(assignment)
);
assert(studyAfterReset.studied === 2 &&
    studyAfterReset.correct === 1 &&
    studyAfterReset.revisit === 1,
  "study results should remain readable after homework reset");
assert(localStorage.getItem(REVIEW_LS) === reviewBeforeStudy &&
    localStorage.getItem(EVENTS_LS) === eventsBeforeStudy &&
    localStorage.getItem(QA_LS) === qaBeforeStudy,
  "homework reset must not disturb review history or Q&A sentinels");

runtime.state.homeworkId = assignment.id;
runtime.state.homeworkStudyWordId = cafe.id;
runtime.state.homeworkStudyAnswer = "caffee";
runtime.state.homeworkStudyAnswerCorrect = null;
runtime.state.homeworkStudyAnswerVerdict = "";
runtime.state.homeworkStudyRevealed = false;
assert(runtime.recordHomeworkStudyResult("typed") === true,
  "a caffee near miss should persist as a studied response");
assert(runtime.state.homeworkStudyAnswerCorrect === false &&
    runtime.state.homeworkStudyAnswerVerdict === "near_miss",
  "the study card state must distinguish a near miss from correct and incorrect");
const cafeProgress = runtime.homeworkStudyProgress(assignment);
assert(cafeProgress.responses[cafe.id].answer === "caffee" &&
    cafeProgress.responses[cafe.id].answerVerdict === "near_miss" &&
    cafeProgress.responses[cafe.id].answerCorrect === false &&
    cafeProgress.responses[cafe.id].correctCount === 0,
  "the near-miss verdict and original answer must survive a fresh progress read");
studyCardHtml = runtime.dashboardHomeworkStudyCardHtml(assignment);
assert(studyCardHtml.includes("homework-study-result is-near_miss") &&
    studyCardHtml.includes("拼写") &&
    studyCardHtml.includes("参考拼写：coffee") &&
    !studyCardHtml.includes("暂时不对"),
  "caffee should render the yellow near-miss state with a coffee suggestion");
"""


def test_homework_study_runtime_and_option_meanings(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the inline homework study runtime test")

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
        "Node homework study runtime regression failed\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
