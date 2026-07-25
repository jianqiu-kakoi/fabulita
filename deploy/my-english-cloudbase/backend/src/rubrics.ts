import { ApiError } from "./errors";

export interface MeaningPattern {
  all: string[];
  none?: string[];
}

export interface ServerScoringRubric {
  assignmentId: string;
  sectionId: string;
  itemId: string;
  task: string;
  cue: string;
  canonicalAnswer: string;
  acceptedAnswers: string[];
  intent: string;
  meaningPatterns: MeaningPattern[];
  polishNote: string;
  ambiguityNote: string;
  level: string;
  language: string;
  rubricVersion: string;
}

const HOTEL_SECTION = "hotel-check-in-roleplay";
const RUBRIC_VERSION = "my-english-hotel-check-in-2026-07-25";

const HOTEL_RUBRICS: Record<string, Omit<ServerScoringRubric,
  "assignmentId" | "sectionId" | "itemId" | "level" | "language" | "rubricVersion"
>> = {
  "hc-scene-01": {
    task: "告诉酒店前台你想办理入住。",
    cue: "Good evening. Welcome to the Maple Hotel. How can I help you?",
    canonicalAnswer: "I'd like to check in, please.",
    acceptedAnswers: [
      "I'd like to check in, please.",
      "I would like to check in, please.",
      "I'm here to check in.",
      "Can I check in, please?",
      "I have a reservation.",
      "I have a booking.",
    ],
    intent: "request_check_in",
    meaningPatterns: [
      { all: ["check", "in"], none: ["not", "cannot", "can't", "don't"] },
      { all: ["reservation"], none: ["not", "cannot", "can't", "don't"] },
      { all: ["booking"], none: ["not", "cannot", "can't", "don't"] },
    ],
    polishNote:
      "意思已经表达清楚；更自然、礼貌的说法是：I'd like to check in, please.",
    ambiguityNote: "表达入住意图或说明已有预订都可以。",
  },
  "hc-scene-02": {
    task: "告诉前台预订登记在 Chen 名下。",
    cue: "What name is the reservation under?",
    canonicalAnswer: "The reservation is under the name Chen.",
    acceptedAnswers: [
      "Chen.",
      "Under Chen.",
      "It's under Chen.",
      "It's under the name Chen.",
      "The reservation is under Chen.",
      "The reservation is under the name Chen.",
      "I have a booking under Chen.",
    ],
    intent: "give_reservation_name",
    meaningPatterns: [
      { all: ["chen"], none: ["not", "isn't", "isnt"] },
    ],
    polishNote:
      "意思已经表达清楚；完整说法可以是：The reservation is under the name Chen.",
    ambiguityNote: "直接回答姓名或使用完整句子都可以。",
  },
  "hc-scene-03": {
    task: "把护照递给前台。",
    cue: "May I see your passport, please?",
    canonicalAnswer: "Sure. Here you are.",
    acceptedAnswers: [
      "Sure. Here you are.",
      "Of course. Here you are.",
      "Certainly. Here you are.",
      "Here you are.",
      "Here you go.",
      "Sure.",
    ],
    intent: "hand_over_passport",
    meaningPatterns: [
      { all: ["here", "you", "are"], none: ["not", "cannot", "can't"] },
      { all: ["here", "you", "go"], none: ["not", "cannot", "can't"] },
      { all: ["sure"], none: ["not", "cannot", "can't"] },
    ],
    polishNote: "递交物品时可以说：Sure. Here you are.",
    ambiguityNote: "表示同意并递交证件的常见自然表达都可以。",
  },
  "hc-scene-04": {
    task: "询问几点退房。",
    cue: "You booked a double room for two nights. Breakfast is included.",
    canonicalAnswer: "What time is checkout?",
    acceptedAnswers: [
      "What time is checkout?",
      "When is checkout?",
      "What is the checkout time?",
      "What time do I need to check out?",
      "When should I check out?",
    ],
    intent: "ask_checkout_time",
    meaningPatterns: [
      { all: ["checkout", "time"], none: ["not", "don't"] },
      { all: ["when", "checkout"], none: ["not", "don't"] },
      { all: ["what", "time", "check", "out"], none: ["not", "don't"] },
    ],
    polishNote: "更自然的问法是：What time is checkout?",
    ambiguityNote: "checkout 是名词；check out 是动词短语，两种结构都可以。",
  },
  "hc-scene-05": {
    task: "询问酒店 Wi-Fi 密码。",
    cue:
      "Checkout is at 11 a.m. Your room is 508, on the fifth floor. Here is your key card.",
    canonicalAnswer: "Could I have the Wi-Fi password, please?",
    acceptedAnswers: [
      "Could I have the Wi-Fi password, please?",
      "Can I have the Wi-Fi password, please?",
      "May I have the Wi-Fi password, please?",
      "Could you tell me the Wi-Fi password, please?",
      "What is the Wi-Fi password?",
      "What's the hotel Wi-Fi password?",
      "Wi-Fi password, please.",
    ],
    intent: "ask_wifi_password",
    meaningPatterns: [
      { all: ["wifi", "password"], none: ["not", "don't"] },
    ],
    polishNote:
      "意思表达正确；询问密码时通常要加 the。更自然的说法是：What is the Wi-Fi password?",
    ambiguityNote:
      "could / can / may，以及 Wi-Fi、WiFi、Wi Fi 等常见写法都可以。",
  },
  "hc-scene-06": {
    task: "表示没有别的问题并道谢。",
    cue: "The Wi-Fi password is MAPLE508. Is there anything else?",
    canonicalAnswer: "No, that's all. Thank you.",
    acceptedAnswers: [
      "No, that's all. Thank you.",
      "That's all. Thank you.",
      "No, thank you.",
      "No, thanks.",
      "I'm all set, thank you.",
      "Nothing else, thank you.",
      "I'm good, thank you.",
    ],
    intent: "close_conversation_politely",
    meaningPatterns: [
      { all: ["all", "thank"] },
      { all: ["nothing", "thank"] },
      { all: ["no", "thank"] },
    ],
    polishNote: "可以说：No, that's all. Thank you.",
    ambiguityNote: "表示不需要其他帮助并礼貌结束对话即可。",
  },
};

export function findScoringRubric(
  assignmentId: string,
  sectionId: string,
  itemId: string,
): ServerScoringRubric {
  if (
    assignmentId !== "hotel-check-in-a1" ||
    sectionId !== HOTEL_SECTION ||
    !HOTEL_RUBRICS[itemId]
  ) {
    throw new ApiError(
      "RUBRIC_NOT_FOUND",
      "This exercise is not enabled for server scoring.",
      404,
    );
  }
  return {
    assignmentId,
    sectionId,
    itemId,
    level: "A1-A2",
    language: "en",
    rubricVersion: RUBRIC_VERSION,
    ...HOTEL_RUBRICS[itemId],
  };
}
