import shutil
import subprocess
from pathlib import Path

import pytest

from fabulita import build, stories, vocab
from fabulita.project import Project


REPO = Path(__file__).parent.parent
MY_ENGLISH = REPO / "examples" / "my-english"


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
  window.__myEnglishRuntimeTest = {
    state,
    targetLanguageLabel,
    supportLanguageLabel,
    reviewAnswerPlaceholder,
    exportFileSlug,
    dashboardHtml,
    reviewAnswerMatches,
    reviewContexts,
    vocabWords,
    reviewScopeKey,
    historyScopeKey,
    qaScopeKey,
    homeworkScopeKey,
    homeworkAssignments,
    homeworkById,
    homeworkVerdict,
    homeworkMeaningMatches,
    checkHomeworkAnswer,
    homeworkProgress,
    queueHomeworkWeakWordsForReview,
    reviewBuckets,
    reviewStore,
    openHomework,
    openHomeworkScenarioTeaching,
    startHomeworkScenarioExercise,
    homeworkScenarioActiveTab,
    dashboardHomeworkScenarioTabsHtml,
    dashboardHomeworkScenarioTeachingHtml,
    targetVoice
  };
` + application.slice(close);

const storage = new Map();
const documentListeners = {};
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
  addEventListener(type, handler) {
    if (!documentListeners[type]) documentListeners[type] = [];
    documentListeners[type].push(handler);
  },
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

function dispatchClosestClick(selector, dataset = {}) {
  const element = {
    dataset,
    classList,
    disabled: false,
    textContent: "",
    setAttribute: noop,
    removeAttribute: noop
  };
  const target = {
    closest(query) {
      return query === selector ? element : null;
    }
  };
  (documentListeners.click || []).forEach((handler) => {
    handler({ target, preventDefault: noop });
  });
  return element;
}

const spokenTexts = [];
class SpeechSynthesisUtteranceStub {
  constructor(text) {
    this.text = String(text || "");
    this.onend = null;
    this.onerror = null;
  }
}

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
  speechSynthesis: {
    cancel: noop,
    getVoices: () => [{ lang: "es-ES", name: "Spanish" }, { lang: "en-US", name: "English" }],
    speak(utterance) {
      spokenTexts.push(utterance.text);
      if (typeof utterance.onend === "function") utterance.onend();
    }
  },
  SpeechSynthesisUtterance: SpeechSynthesisUtteranceStub,
  Audio: AudioStub
};
context.window = context;

vm.createContext(context);
vm.runInContext(application, context);

const runtime = context.__myEnglishRuntimeTest;
const HOMEWORK_LS = "fabulita.homework.v1";
assert(runtime, "runtime test API was not exposed");
assert(P.config.name === "My English", "wrong English app name");
assert(P.config.lang === "en" && P.config.layout === "vocab", "wrong English dashboard config");
assert(runtime.targetLanguageLabel() === "英语", "target language label should be English");
assert(runtime.supportLanguageLabel() === "英语解释", "support column should be an English definition");
assert(runtime.reviewAnswerPlaceholder().includes("the first part of the day"),
  "English cards need a meaning-based answer example");
assert(runtime.exportFileSlug() === "my-english", "wrong export filename scope");
assert(runtime.reviewScopeKey === "book:my-english-core-v1:en", "review scope leaked");
assert(runtime.historyScopeKey === "book:my-english:en", "history scope leaked");
assert(runtime.qaScopeKey === "book:my-english:en", "Q&A scope leaked");
assert(runtime.homeworkScopeKey === "book:my-english:en", "homework scope leaked");
assert(runtime.targetVoice && runtime.targetVoice.lang === "en-US", "English voice was not selected");

const dashboard = runtime.dashboardHtml();
assert(dashboard.includes("My English"), "English brand is missing");
assert(dashboard.includes("英语词表"), "English dashboard title is missing");
assert(dashboard.includes("英语解释"), "English definition column is missing");
assert(!dashboard.includes('<p class="vocab-brand">Mi Español</p>'),
  "Spanish brand leaked into My English");

const morning = runtime.vocabWords.find((word) => word.w === "morning");
const wakeUp = runtime.vocabWords.find((word) => word.w === "wake up");
const grammar = runtime.vocabWords.find((word) => word.w === "be");
assert(morning && wakeUp && grammar, "representative English cards are missing");
assert(runtime.reviewAnswerMatches(morning, "早上") === true, "natural Chinese meaning should pass");
assert(runtime.reviewAnswerMatches(morning, "first part of the day") === true,
  "English noun definition without its article should pass");
assert(runtime.reviewAnswerMatches(morning, "morning") === false,
  "typing the visible headword must not count as knowing its meaning");
assert(runtime.reviewAnswerMatches(wakeUp, "stop sleeping") === true,
  "phrasal-verb definition without to should pass");
assert(runtime.reviewAnswerMatches(grammar, "是") === false,
  "grammar reference rows must stay out of meaning review");
assert(runtime.reviewContexts.morning && runtime.reviewContexts.morning.sent,
  "the accepted story should provide a review context for morning");

assert(runtime.homeworkAssignments.length === 3, "English homework assignments are missing");
runtime.state.dashboardNav = "homework";
const homework = runtime.dashboardHtml();
assert(homework.includes("日常英语词汇练习 A1"), "English vocabulary homework is missing");
assert(homework.includes("Be 动词与一般现在时 A1"), "English grammar homework is missing");
assert(homework.includes("Hotel Check-in"), "hotel check-in homework is missing");
assert(homework.includes("CC BY 4.0"), "hotel content license is missing from the homework list");
assert(!homework.includes("查看原教材 PDF"),
  "the hotel card should not promote the source PDF as a primary action");
assert(!homework.includes("Ser / Estar 与词汇练习 A0"), "Spanish homework leaked into English");

const hotel = runtime.homeworkById("hotel-check-in-a1");
assert(hotel, "hotel check-in assignment is not addressable by id");
const hotelItems = hotel.sections.flatMap((section) => section.items);
assert(hotelItems.length === 6, "hotel check-in must stay a six-step scenario");
assert(runtime.homeworkVerdict(hotelItems[0], "I’d like to check in, please!") === "correct",
  "smart apostrophes and harmless final punctuation should be accepted");
assert(runtime.homeworkVerdict(hotelItems[4], "Could I have the WiFi password, please?") === "correct",
  "WiFi should match the authored Wi-Fi answer");
assert(runtime.homeworkVerdict(hotelItems[4], "Could I have the Wi Fi password, please?") === "correct",
  "Wi Fi should match the authored Wi-Fi answer");
assert(runtime.homeworkVerdict(hotelItems[4], "What is wifi password") === "near_miss",
  "a clear Wi-Fi-password request with a missing article should be meaning-correct");
assert(runtime.homeworkMeaningMatches(hotelItems[4], "What is wifi password") === true,
  "the local intent fallback should recognize the Wi-Fi-password request");
assert(runtime.homeworkVerdict(hotelItems[4], "Where is breakfast?") === "incorrect",
  "natural matching must not accept an unrelated hotel sentence");
const reviewCardsBeforeMeaningMatch = Object.keys(runtime.reviewStore.cards).length;
assert(runtime.queueHomeworkWeakWordsForReview(
  hotel, hotelItems[4], "near_miss", "What is wifi password"
) === 0, "a meaning-correct answer should not be treated as unknown vocabulary");
assert(Object.keys(runtime.reviewStore.cards).length === reviewCardsBeforeMeaningMatch,
  "a meaning-correct answer must not add a vocabulary review card");
assert(runtime.queueHomeworkWeakWordsForReview(hotel, hotelItems[0], "incorrect") === 1,
  "an incorrect hotel answer should queue its related word");
const queuedReview = runtime.reviewBuckets(Date.now()).due;
assert(queuedReview.some((word) => word.w === "check in"),
  "a queued homework word should become immediately due in review");
assert(runtime.reviewStore.cards["w:check in"].homeworkAssignmentId === "hotel-check-in-a1",
  "queued review metadata should retain its homework source");
assert(runtime.queueHomeworkWeakWordsForReview(hotel, hotelItems[0], "correct") === 0,
  "a correct hotel answer must not add review work");

runtime.openHomework(hotel);
const hotelIntro = runtime.dashboardHtml();
assert(hotelIntro.includes("TRAVEL ENGLISH"), "hotel scenario intro is missing");
assert(hotelIntro.includes("在酒店办理入住"), "hotel scenario goal is missing");
assert(hotelIntro.includes("说明入住意图"), "hotel six-step route is missing");
assert(hotelIntro.includes("English for Tourism Professionals"),
  "hotel source attribution is missing from the scenario");
assert(hotelIntro.includes("CC BY 4.0"), "hotel content license is missing from the scenario");
assert(hotelIntro.includes("教材来源"), "hotel source link is missing from the attribution");
assert(hotelIntro.includes("开始场景教学"), "hotel intro should lead into teaching before practice");
assert(!hotelIntro.includes("查看原教材 PDF"),
  "the scenario intro should not promote the source PDF as a primary action");

assert(runtime.openHomeworkScenarioTeaching(hotel) === true,
  "the hotel scenario should enter the teaching state");
assert(runtime.state.homeworkScenarioTeaching === true &&
    runtime.state.homeworkScenarioIntro === false,
  "teaching should replace the scenario intro");
const hotelTeaching = runtime.dashboardHtml();
assert(hotelTeaching.includes("先看一遍完整入住对话"),
  "the complete-dialogue teaching title is missing");
assert(hotelTeaching.includes("播放完整对话"), "the complete-dialogue playback action is missing");
assert(hotelTeaching.includes("Good evening. Welcome to the Maple Hotel."),
  "the teaching dialogue is missing its opening English line");
assert(hotelTeaching.includes("晚上好。欢迎来到枫叶酒店。有什么可以帮您？"),
  "the teaching dialogue is missing its opening Chinese line");
assert(hotelTeaching.includes("You're welcome. Enjoy your stay."),
  "the teaching dialogue is missing its closing English line");
assert(hotelTeaching.includes("不客气。祝您入住愉快。"),
  "the teaching dialogue is missing its closing Chinese line");
assert((hotelTeaching.match(/<article class="homework-teaching-line/g) || []).length === 13,
  "the teaching page should render all 13 dialogue turns");
assert((hotelTeaching.match(/data-homework-answer-speak=/g) || []).length === 13,
  "every teaching turn should have a pronunciation control");
assert(hotelTeaching.includes("下一步：核心词汇"),
  "the teaching page should lead into the core-vocabulary tab");
assert(!hotelTeaching.includes('id="homework-answer-form"'),
  "the answer form must stay hidden during scenario teaching");
assert(!hotelTeaching.includes("查看原教材 PDF"),
  "the teaching page should not promote the source PDF as a primary action");
const teachingTabs = runtime.dashboardHomeworkScenarioTabsHtml(hotel);
assert((teachingTabs.match(/<button class="homework-course-tab(?: |")/g) || []).length === 3,
  "the hotel detail should expose exactly three course tabs after its intro");
assert(teachingTabs.includes('data-homework-tab="teaching"') &&
    teachingTabs.includes("场景教学"),
  "the scenario-teaching tab is missing");
assert(teachingTabs.includes('data-homework-tab="vocabulary"') &&
    teachingTabs.includes("核心词汇"),
  "the core-vocabulary tab is missing");
assert(teachingTabs.includes('data-homework-tab="practice"') &&
    teachingTabs.includes("六步练习"),
  "the six-step-practice tab is missing");
assert(teachingTabs.includes(
  'data-homework-tab="teaching" aria-current="step"'
), "the teaching tab should be active while the dialogue lesson is open");
assert(hotelTeaching.includes(teachingTabs),
  "the three course tabs should be rendered in the hotel detail page");
const teachingHeaderMatch = hotelTeaching.match(
  /<header class="homework-detail-head">([\s\S]*?)<\/header>/
);
assert(teachingHeaderMatch, "the hotel detail header is missing");
assert(!teachingHeaderMatch[1].includes('data-homework-study-open') &&
    !teachingHeaderMatch[1].includes('data-homework-action="start-exercise"'),
  "scenario tabs should replace the old vocabulary/practice header buttons");
assert(!teachingHeaderMatch[1].includes("继续学单词") &&
    !teachingHeaderMatch[1].includes("继续作业"),
  "legacy continue buttons should not remain in the scenario header");

const bookedTerm = hotelTeaching.match(
  /<button class="homework-teaching-term"[^>]*data-homework-teaching-word="([^"]+)"[^>]*data-homework-teaching-word-id="hc-book-verb"[^>]*aria-expanded="false"[^>]*>booked<\/button>/
);
assert(bookedTerm, "booked should render as a clickable teaching word");
assert(!hotelTeaching.includes("homework-teaching-word-card"),
  "a teaching word should stay collapsed before it is clicked");
dispatchClosestClick("[data-homework-teaching-word]", {
  homeworkTeachingWord: bookedTerm[1],
  homeworkTeachingWordId: "hc-book-verb"
});
assert(runtime.state.homeworkTeachingWordKey === bookedTerm[1],
  "clicking booked should select its teaching-word key");
const bookedExpanded = runtime.dashboardHtml();
assert(bookedExpanded.includes("homework-teaching-word-card"),
  "clicking booked should open its teaching-word card");
assert(bookedExpanded.includes('<strong lang="en">book</strong>'),
  "the expanded booked card should show the headword book");
assert(bookedExpanded.includes(
  '<p class="homework-teaching-word-gloss">预订</p>'
), "the expanded booked card should show its Chinese meaning");
assert(bookedExpanded.includes(
  '<p class="homework-teaching-word-english" lang="en">to arrange for a hotel room before you arrive</p>'
), "the expanded booked card should show its English definition");
dispatchClosestClick("[data-homework-teaching-word]", {
  homeworkTeachingWord: bookedTerm[1],
  homeworkTeachingWordId: "hc-book-verb"
});
assert(runtime.state.homeworkTeachingWordKey === "",
  "clicking the same teaching word twice should collapse it");
assert(!runtime.dashboardHtml().includes("homework-teaching-word-card"),
  "the teaching-word card should be removed after the second click");

runtime.state.homeworkDialogueTranslations = false;
const hotelTeachingEnglishOnly = runtime.dashboardHtml();
assert(hotelTeachingEnglishOnly.includes("显示中文"),
  "the English-only teaching view should offer to restore translations");
assert(!hotelTeachingEnglishOnly.includes("不客气。祝您入住愉快。"),
  "Chinese dialogue lines should be hidden in English-only mode");
runtime.state.homeworkDialogueTranslations = true;

assert(runtime.homeworkProgress(hotel).lastTab === "teaching",
  "opening scenario teaching should persist the active tab");
dispatchClosestClick("[data-homework-tab]", { homeworkTab: "vocabulary" });
assert(runtime.state.homeworkStudyOpen === true &&
    runtime.state.homeworkScenarioTeaching === false &&
    runtime.homeworkScenarioActiveTab() === "vocabulary",
  "the vocabulary tab should switch the hotel detail into word study");
assert(runtime.homeworkProgress(hotel).lastTab === "vocabulary",
  "the vocabulary tab should be written to homework progress");
const hotelVocabulary = runtime.dashboardHtml();
assert(hotelVocabulary.includes(
  'data-homework-tab="vocabulary" aria-current="step"'
), "the vocabulary tab should render as active");
assert(!hotelVocabulary.includes("查看原教材 PDF"),
  "the vocabulary tab should preserve scenario PDF hiding");
runtime.openHomework(hotel);
assert(runtime.state.homeworkStudyOpen === true &&
    runtime.homeworkScenarioActiveTab() === "vocabulary",
  "reopening the hotel should restore its vocabulary tab");

dispatchClosestClick("[data-homework-tab]", { homeworkTab: "practice" });
assert(runtime.state.homeworkStudyOpen === false &&
    runtime.state.homeworkScenarioTeaching === false &&
    runtime.state.homeworkScenarioIntro === false &&
    runtime.homeworkScenarioActiveTab() === "practice",
  "the practice tab should switch the hotel detail into the six-step exercise");
assert(runtime.homeworkProgress(hotel).lastTab === "practice",
  "the practice tab should be written to homework progress");
assert(runtime.dashboardHtml().includes('id="homework-answer-form"'),
  "the practice tab should render the answer form");
runtime.openHomework(hotel);
assert(runtime.homeworkScenarioActiveTab() === "practice" &&
    runtime.state.homeworkScenarioIntro === false,
  "reopening the hotel should restore its practice tab");

dispatchClosestClick("[data-homework-tab]", { homeworkTab: "teaching" });
assert(runtime.state.homeworkScenarioTeaching === true &&
    runtime.homeworkScenarioActiveTab() === "teaching",
  "the teaching tab should switch back to the dialogue lesson");
assert(runtime.homeworkProgress(hotel).lastTab === "teaching",
  "the teaching tab should be written to homework progress");
runtime.openHomework(hotel);
assert(runtime.state.homeworkScenarioTeaching === true &&
    runtime.homeworkScenarioActiveTab() === "teaching",
  "reopening the hotel should restore its teaching tab");

dispatchClosestClick("[data-homework-tab]", { homeworkTab: "practice" });
runtime.state.homeworkRetryIds = ["hc-scene-02", "hc-scene-05"];
runtime.state.homeworkIndex = 4;
runtime.state.homeworkSummary = true;
const retryContext = JSON.stringify(runtime.state.homeworkRetryIds);
dispatchClosestClick("[data-homework-tab]", { homeworkTab: "teaching" });
assert(JSON.stringify(runtime.state.homeworkRetryIds) === retryContext &&
    runtime.state.homeworkIndex === 4 &&
    runtime.state.homeworkSummary === true,
  "the teaching tab should preserve practice retry, position, and summary context");
dispatchClosestClick("[data-homework-tab]", { homeworkTab: "vocabulary" });
assert(JSON.stringify(runtime.state.homeworkRetryIds) === retryContext &&
    runtime.state.homeworkIndex === 4 &&
    runtime.state.homeworkSummary === true,
  "the vocabulary tab should preserve practice retry, position, and summary context");
dispatchClosestClick("[data-homework-tab]", { homeworkTab: "practice" });
assert(JSON.stringify(runtime.state.homeworkRetryIds) === retryContext &&
    runtime.state.homeworkIndex === 4 &&
    runtime.state.homeworkSummary === true,
  "returning to practice should restore the same retry, position, and summary context");
runtime.state.homeworkRetryIds = [];
runtime.state.homeworkIndex = 0;
runtime.state.homeworkSummary = false;

const completedTabRoot = JSON.parse(localStorage.getItem(HOMEWORK_LS));
const completedTabRecord =
  completedTabRoot.scopes[runtime.homeworkScopeKey].assignments[hotel.id];
completedTabRecord.completedAt = Date.now();
completedTabRecord.lastTab = "teaching";
localStorage.setItem(HOMEWORK_LS, JSON.stringify(completedTabRoot));
runtime.openHomework(hotel);
assert(runtime.state.homeworkScenarioTeaching === true &&
    runtime.state.homeworkSummary === true,
  "a completed hotel should still restore its last teaching tab");
dispatchClosestClick("[data-homework-tab]", { homeworkTab: "practice" });
assert(runtime.state.homeworkSummary === true &&
    runtime.dashboardHtml().includes("本次作业结果"),
  "switching a completed hotel to practice should preserve its result summary");
const resetCompletedRoot = JSON.parse(localStorage.getItem(HOMEWORK_LS));
resetCompletedRoot.scopes[runtime.homeworkScopeKey]
  .assignments[hotel.id].completedAt = null;
resetCompletedRoot.scopes[runtime.homeworkScopeKey]
  .assignments[hotel.id].lastTab = "teaching";
localStorage.setItem(HOMEWORK_LS, JSON.stringify(resetCompletedRoot));
runtime.openHomework(hotel);

assert(runtime.startHomeworkScenarioExercise(hotel) === true,
  "teaching should transition into the scenario exercise");
assert(runtime.state.homeworkScenarioTeaching === false &&
    runtime.state.homeworkScenarioIntro === false &&
    runtime.state.homeworkIndex === 0,
  "starting the exercise should clear teaching state and begin at step one");
const hotelQuestion = runtime.dashboardHtml();
assert(hotelQuestion.includes("Good evening. Welcome to the Maple Hotel."),
  "hotel front-desk cue is missing");
assert(hotelQuestion.includes("告诉前台你想办理入住"), "hotel learner task is missing");
assert(hotelQuestion.includes('id="homework-answer-form"'),
  "the six-step exercise should render an answer form");
assert(!hotelQuestion.includes("查看原教材 PDF"),
  "the exercise should not promote the source PDF as a primary action");

runtime.state.homeworkStudyOpen = true;
runtime.state.homeworkStudyWordId = "hc-reservation";
runtime.state.homeworkStudyRevealed = true;
const hotelStudy = runtime.dashboardHtml();
assert(hotelStudy.includes("/ˌrez.ɚˈveɪ.ʃən/"),
  "hotel study card is missing pronunciation");
assert(hotelStudy.includes("我有一个登记在 Chen 名下的预订。"),
  "hotel study card is missing the translated example");

runtime.startHomeworkScenarioExercise(hotel);
runtime.state.homeworkIndex = 4;
const reviewCardsBeforeCheckedMeaning = Object.keys(runtime.reviewStore.cards).length;
assert(runtime.checkHomeworkAnswer("What is wifi password") === true,
  "the meaning-correct Wi-Fi answer should be checkable");
const meaningProgress = runtime.homeworkProgress(hotel);
assert(meaningProgress.responses["hc-scene-05"].status === "near_miss",
  "the persisted Wi-Fi answer should use the middle verdict");
assert(Object.keys(runtime.reviewStore.cards).length === reviewCardsBeforeCheckedMeaning,
  "checking a meaning-correct answer must not create vocabulary review work");
const meaningFeedback = runtime.dashboardHtml();
assert(meaningFeedback.includes("意思表达对了，可以更自然"),
  "the middle verdict should explain that the intended meaning is correct");
assert(meaningFeedback.includes("询问密码时通常要加 the"),
  "the middle verdict should explain the missing article");
assert(!meaningFeedback.includes("意思对了，再注意一下拼写"),
  "a naturalness issue must not be mislabeled as a spelling issue");
assert(!meaningFeedback.includes("查看原教材 PDF"),
  "answer feedback should not promote the source PDF as a primary action");

runtime.state.homeworkSummary = true;
const hotelSummary = runtime.dashboardHtml();
assert(hotelSummary.includes("意思正确，可优化"),
  "the scenario summary should preserve the three-level verdict language");
assert(!hotelSummary.includes("查看原教材 PDF"),
  "the scenario summary should not promote the source PDF as a primary action");

runtime.state.homeworkScenarioIntro = true;
runtime.state.homeworkScenarioTeaching = false;
dispatchClosestClick("[data-homework-action]", { homeworkAction: "start-teaching" });
assert(runtime.state.homeworkScenarioTeaching === true,
  "the rendered start-teaching action should be wired to the teaching state");
const translationsBeforeClick = runtime.state.homeworkDialogueTranslations;
dispatchClosestClick("[data-homework-action]", { homeworkAction: "toggle-translations" });
assert(runtime.state.homeworkDialogueTranslations !== translationsBeforeClick,
  "the rendered translation toggle should update teaching state");
const spokenBeforeDialogue = spokenTexts.length;
dispatchClosestClick("[data-homework-dialogue-play]");
const playedDialogue = spokenTexts.slice(spokenBeforeDialogue).join(" ");
assert(playedDialogue.includes("Good evening. Welcome to the Maple Hotel."),
  "complete-dialogue playback should speak the opening line");
assert(playedDialogue.includes("You're welcome. Enjoy your stay."),
  "complete-dialogue playback should reach the closing line");
dispatchClosestClick("[data-homework-action]", { homeworkAction: "start-exercise" });
assert(runtime.state.homeworkScenarioTeaching === false &&
    runtime.state.homeworkScenarioIntro === false,
  "the rendered exercise action should leave teaching and intro states");
"""


def _clean_project(tmp_path):
    project_root = tmp_path / "my-english"
    shutil.copytree(MY_ENGLISH, project_root)
    project = Project(project_root)
    project.save_vocab([])
    vocab.import_file(project, project_root / "vocab.csv")
    return project


def test_my_english_data_and_build(tmp_path):
    project = _clean_project(tmp_path)
    words = project.vocab
    assert len(words) == 77
    assert len({word["w"].casefold() for word in words}) == 77

    grammar = [word for word in words if word.get("review_mode") == "grammar"]
    meaning = [word for word in words if word.get("review_mode", "meaning") == "meaning"]
    assert len(grammar) == 4
    assert len(meaning) == 73
    assert all(word.get("kind") == "grammar" for word in grammar)

    allowed_kinds = {
        "noun", "adverb", "phrase", "phrasal verb", "verb",
        "adjective", "preposition", "conjunction",
    }
    for word in meaning:
        assert word.get("kind") in allowed_kinds, word["w"]
        for field in ("note", "category", "example", "example_trans", "answers"):
            assert word.get(field), (word["w"], field)

    by_word = {word["w"]: word for word in words}
    assert "早上" in by_word["morning"]["answers"].split("|")
    assert "to stop sleeping" in by_word["wake up"]["answers"].split("|")
    assert "morning" not in by_word["morning"]["answers"].split("|")

    assert project.config["name"] == "My English"
    assert project.config["lang"] == "en"
    assert project.config["layout"] == "vocab"
    assert project.config["review_id"] == "my-english-core-v1"
    for key in ("qa_id", "history_id", "homework_id"):
        assert project.config[key] == "my-english"

    all_stories = project.stories()
    assert len(all_stories) == 1
    errors, warnings = stories.validate(project, all_stories[0])
    assert errors == []
    assert warnings == []

    assignments = project.homeworks
    assert len(assignments) == 3
    by_assignment = {assignment["id"]: assignment for assignment in assignments}
    vocabulary = by_assignment["everyday-english-a1"]
    grammar_assignment = by_assignment["be-and-present-simple-a1"]
    hotel = by_assignment["hotel-check-in-a1"]
    assert len(vocabulary["studyWords"]) == 28
    assert sum(len(section["items"]) for section in vocabulary["sections"]) == 24
    assert sum(len(section["items"]) for section in grammar_assignment["sections"]) == 16
    assert vocabulary["answerKeyBasis"] == "standard_usage"
    assert grammar_assignment["answerKeyBasis"] == "standard_grammar"
    assert hotel["answerKeyBasis"] == "authored_adaptation"
    assert hotel["layout"] == "dialogue"
    assert hotel["navigation"] == "sequential"
    assert hotel["reviewBridge"] is True

    dialogue = hotel["scenario"]["dialogue"]
    assert len(dialogue) == 13
    assert [line["speaker"] for line in dialogue] == [
        "Desk clerk" if index % 2 == 0 else "Guest"
        for index in range(13)
    ]
    assert all(line.get("english") and line.get("chinese") for line in dialogue)
    guest_turns = [line for line in dialogue if line["speaker"] == "Guest"]
    assert [line["learnerStep"] for line in guest_turns] == list(range(1, 7))
    assert dialogue[-1]["english"] == "You're welcome. Enjoy your stay."
    assert dialogue[-1]["chinese"] == "不客气。祝您入住愉快。"

    sentence_lexicon = {
        entry["id"]: entry
        for entry in hotel["sentenceLexicon"]
    }
    booked = sentence_lexicon["hc-book-verb"]
    assert booked["word"] == "book"
    assert booked["forms"] == ["booked"]
    assert booked["gloss"] == "预订"
    assert booked["english"] == "to arrange for a hotel room before you arrive"

    hotel_words = hotel["studyWords"]
    assert len(hotel_words) == 12
    assert len({word["word"].casefold() for word in hotel_words}) == 12
    assert all(word.get("pronunciation", "").startswith("/") for word in hotel_words)

    hotel_items = [
        item
        for section in hotel["sections"]
        for item in section["items"]
    ]
    assert len(hotel_items) == 6
    assert [item["number"] for item in hotel_items] == list(range(1, 7))
    assert all(item.get("scene", {}).get("cue") for item in hotel_items)
    assert all(item.get("canonicalAnswer") in item["answers"] for item in hotel_items)
    assert all(item.get("intent") for item in hotel_items)
    assert all(item.get("meaningPatterns") for item in hotel_items)
    assert all(item.get("polishNote") for item in hotel_items)
    for item, guest_turn in zip(hotel_items, guest_turns):
        assert guest_turn["english"] == item["canonicalAnswer"]
        assert guest_turn["chinese"] == item["answerTranslation"]

    vocab_keys = {word["w"].casefold() for word in words}
    hotel_word_keys = {word["word"].casefold() for word in hotel_words}
    review_word_keys = {
        review_word.casefold()
        for item in hotel_items
        for review_word in item.get("reviewWords", [])
    }
    assert hotel_word_keys <= vocab_keys
    assert review_word_keys == hotel_word_keys

    source = hotel["source"]
    assert source["url"].startswith("https://")
    assert source["licenseUrl"].startswith("https://")
    assert source["license"] == "CC BY 4.0"
    assert hotel["contentLicense"]["spdx"] == "CC-BY-4.0"
    assert source["thirdPartyImagesReused"] is False
    for assignment in assignments:
        assert assignment.get("answerKeyBasis") != "inferred_from_context"
        item_ids = [
            item["id"]
            for section in assignment["sections"]
            for item in section["items"]
        ]
        assert len(item_ids) == len(set(item_ids))
        for section in assignment["sections"]:
            for item in section["items"]:
                assert item.get("answers"), item["id"]
                if section["type"] == "single_choice":
                    assert set(item["answers"]) <= set(item["options"])

    page, size, n_stories, n_clips = build.build(
        project,
        out=tmp_path / "my-english.html",
        include_candidates=False,
        home="index.html",
    )
    html = page.read_text(encoding="utf-8")
    assert size == len(html)
    assert n_stories == 1
    assert n_clips == 0
    assert '"name": "My English"' in html
    assert '"lang": "en"' in html
    assert '"layout": "vocab"' in html
    assert "日常英语词汇练习 A1" in html
    assert "Be 动词与一般现在时 A1" in html
    assert "Hotel Check-in" in html
    assert "You're welcome. Enjoy your stay." in html
    assert "CC BY 4.0" in html


def test_my_english_dashboard_runtime(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the inline dashboard runtime test")

    project = _clean_project(tmp_path)
    page, _, _, _ = build.build(
        project,
        out=tmp_path / "my-english.html",
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
        "Node My English runtime regression failed\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
