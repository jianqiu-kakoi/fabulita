import { ApiError } from "./errors";

export type JsonPrimitive = string | number | boolean | null;
export type JsonValue =
  | JsonPrimitive
  | JsonValue[]
  | { [key: string]: JsonValue };
export type JsonObject = { [key: string]: JsonValue };

export const LEARNING_EVENT_SCHEMA = "fabulita.learning-event.v1";
export const LEARNING_BATCH_SCHEMA = "fabulita.learning-sync-batch.v1";

const EVENT_SOURCES = new Set([
  "review",
  "homework",
  "homework_study",
  "qa",
]);

const EVENT_ACTIONS = new Set([
  "answer_checked",
  "answer_revealed",
  "self_rated",
  "assignment_completed",
  "assignment_reset",
  "question_created",
  "question_deleted",
  "queued_for_review",
]);

const FORBIDDEN_IDENTITY_FIELDS = new Set([
  "userId",
  "uid",
  "owner",
  "ownerId",
  "ownerKey",
  "openId",
  "customUserId",
]);

const EVENT_TEXT_LIMITS: Record<string, number> = {
  projectId: 120,
  language: 20,
  entityId: 180,
  sessionId: 180,
  attemptId: 180,
  legacyEventId: 180,
  assignmentId: 180,
  homeworkItemId: 180,
  sectionId: 180,
  questionType: 80,
  prompt: 500,
  word: 180,
  answerMode: 40,
  submittedAnswer: 500,
  verdict: 40,
  originalVerdict: 40,
  rating: 40,
  matcherVersion: 120,
  scoringSource: 40,
  modelVersion: 120,
  rubricVersion: 120,
  feedbackZh: 500,
  suggestedAnswer: 300,
  cause: 80,
};

const EVENT_NUMBER_FIELDS = [
  "attempt",
  "latencyMs",
  "levelBefore",
  "levelAfter",
  "dueAtBefore",
  "dueAtAfter",
] as const;

export interface LearningEvent extends JsonObject {
  schema: typeof LEARNING_EVENT_SCHEMA;
  id: string;
  occurredAt: number;
  scope: string;
  projectId: string;
  language: string;
  source: string;
  action: string;
  entityId: string;
  sessionId: string;
  attemptId: string;
  legacyEventId: string;
  assignmentId: string;
  homeworkItemId: string;
  sectionId: string;
  questionType: string;
  prompt: string;
  word: string;
  answerMode: string;
  submittedAnswer: string;
  expectedAnswers: string[];
  verdict: string;
  originalVerdict: string;
  rating: string;
  matcherVersion: string;
  scoringSource: string;
  modelVersion: string;
  rubricVersion: string;
  feedbackZh: string;
  suggestedAnswer: string;
  cause: string;
  snapshotPersisted: boolean;
}

export interface SyncBatch {
  schema: typeof LEARNING_BATCH_SCHEMA;
  scope: string;
  events: LearningEvent[];
  currentState: JsonObject;
  baseCheckpointVersion: number;
}

export interface ScoreAnswerInput {
  assignmentId: string;
  sectionId: string;
  itemId: string;
  learnerAnswer: string;
  clientLocalVerdict: string;
}

export type ScoreVerdict = "correct" | "near_miss" | "incorrect";

export interface ScoreAnswerResult {
  verdict: ScoreVerdict;
  meaningCorrect: boolean;
  feedbackZh: string;
  suggestedAnswer: string;
  confidence: number;
  issues: string[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  if (value == null || typeof value !== "object" || Array.isArray(value)) {
    return false;
  }
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

function assertRecord(
  value: unknown,
  field: string,
): asserts value is Record<string, unknown> {
  if (!isRecord(value)) {
    throw new ApiError("INVALID_INPUT", `${field} must be an object.`);
  }
}

function rejectClientIdentity(value: Record<string, unknown>, field: string) {
  for (const key of FORBIDDEN_IDENTITY_FIELDS) {
    if (Object.prototype.hasOwnProperty.call(value, key)) {
      throw new ApiError(
        "CLIENT_IDENTITY_NOT_ALLOWED",
        `${field}.${key} is not accepted; identity comes from CloudBase auth.`,
      );
    }
  }
}

function requiredText(
  value: unknown,
  field: string,
  maxLength: number,
): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new ApiError("INVALID_INPUT", `${field} is required.`);
  }
  const text = value.trim();
  if (text.length > maxLength) {
    throw new ApiError(
      "INVALID_INPUT",
      `${field} must be at most ${maxLength} characters.`,
    );
  }
  return text;
}

function optionalText(value: unknown, maxLength: number): string {
  if (value == null) return "";
  if (typeof value !== "string") {
    throw new ApiError("INVALID_INPUT", "Text fields must be strings.");
  }
  return value.trim().slice(0, maxLength);
}

function jsonByteLength(value: unknown, field: string): number {
  try {
    return new TextEncoder().encode(JSON.stringify(value)).byteLength;
  } catch {
    throw new ApiError("INVALID_INPUT", `${field} must be valid JSON.`);
  }
}

function cloneJsonObject(
  value: unknown,
  field: string,
  maxBytes: number,
): JsonObject {
  assertRecord(value, field);
  if (jsonByteLength(value, field) > maxBytes) {
    throw new ApiError(
      "PAYLOAD_TOO_LARGE",
      `${field} exceeds the ${maxBytes}-byte limit.`,
      413,
    );
  }
  try {
    return JSON.parse(JSON.stringify(value)) as JsonObject;
  } catch {
    throw new ApiError("INVALID_INPUT", `${field} must be valid JSON.`);
  }
}

export function validateScope(value: unknown): string {
  const scope = requiredText(value, "scope", 200);
  if (
    !/^(?:book|self):[a-z0-9][a-z0-9._-]{0,119}:[a-z0-9][a-z0-9-]{0,19}$/i.test(
      scope,
    )
  ) {
    throw new ApiError("INVALID_INPUT", "scope has an invalid format.");
  }
  return scope;
}

function sanitizeEvent(
  raw: unknown,
  scope: string,
  now: number,
): LearningEvent {
  assertRecord(raw, "event");
  rejectClientIdentity(raw, "event");

  if (raw.schema !== LEARNING_EVENT_SCHEMA) {
    throw new ApiError("INVALID_INPUT", "event.schema is not supported.");
  }

  const id = requiredText(raw.id, "event.id", 200);
  if (!/^[\x21-\x7E]+$/.test(id)) {
    throw new ApiError(
      "INVALID_INPUT",
      "event.id must contain printable ASCII characters only.",
    );
  }

  const occurredAt = Number(raw.occurredAt);
  if (
    !Number.isFinite(occurredAt) ||
    occurredAt <= 0 ||
    occurredAt > now + 24 * 60 * 60 * 1000
  ) {
    throw new ApiError("INVALID_INPUT", "event.occurredAt is invalid.");
  }

  if (raw.scope !== scope) {
    throw new ApiError(
      "SCOPE_MISMATCH",
      "Every event scope must match the batch scope.",
    );
  }

  if (typeof raw.source !== "string" || !EVENT_SOURCES.has(raw.source)) {
    throw new ApiError("INVALID_INPUT", "event.source is not supported.");
  }
  if (typeof raw.action !== "string" || !EVENT_ACTIONS.has(raw.action)) {
    throw new ApiError("INVALID_INPUT", "event.action is not supported.");
  }

  const event: LearningEvent = {
    schema: LEARNING_EVENT_SCHEMA,
    id,
    occurredAt,
    scope,
    projectId: "",
    language: "",
    source: raw.source,
    action: raw.action,
    entityId: "",
    sessionId: "",
    attemptId: "",
    legacyEventId: "",
    assignmentId: "",
    homeworkItemId: "",
    sectionId: "",
    questionType: "",
    prompt: "",
    word: "",
    answerMode: "",
    submittedAnswer: "",
    expectedAnswers: [] as string[],
    verdict: "",
    originalVerdict: "",
    rating: "",
    matcherVersion: "",
    scoringSource: "",
    modelVersion: "",
    rubricVersion: "",
    feedbackZh: "",
    suggestedAnswer: "",
    cause: "",
    snapshotPersisted: raw.snapshotPersisted !== false,
  };

  for (const [field, limit] of Object.entries(EVENT_TEXT_LIMITS)) {
    event[field as keyof typeof event] = optionalText(
      raw[field],
      limit,
    ) as never;
  }

  if (Array.isArray(raw.expectedAnswers)) {
    event.expectedAnswers = raw.expectedAnswers
      .filter((answer): answer is string => typeof answer === "string")
      .map((answer) => answer.trim().slice(0, 300))
      .filter(Boolean)
      .slice(0, 50);
  } else if (raw.expectedAnswers != null) {
    throw new ApiError(
      "INVALID_INPUT",
      "event.expectedAnswers must be an array.",
    );
  }

  if (typeof raw.answerCorrect === "boolean" || raw.answerCorrect === null) {
    event.answerCorrect = raw.answerCorrect;
  }
  if (
    typeof raw.meaningCorrect === "boolean" ||
    raw.meaningCorrect === null
  ) {
    event.meaningCorrect = raw.meaningCorrect;
  }
  for (const field of EVENT_NUMBER_FIELDS) {
    if (raw[field] == null) continue;
    const number = Number(raw[field]);
    if (!Number.isFinite(number)) {
      throw new ApiError("INVALID_INPUT", `event.${field} is invalid.`);
    }
    event[field] = number;
  }

  return event;
}

export function validateSyncBatch(
  input: unknown,
  now = Date.now(),
): SyncBatch {
  assertRecord(input, "request");
  rejectClientIdentity(input, "request");

  if (input.schema !== LEARNING_BATCH_SCHEMA) {
    throw new ApiError("INVALID_INPUT", "schema is not supported.");
  }
  const scope = validateScope(input.scope);
  if (!Array.isArray(input.events)) {
    throw new ApiError("INVALID_INPUT", "events must be an array.");
  }
  if (input.events.length > 40) {
    throw new ApiError(
      "PAYLOAD_TOO_LARGE",
      "A sync batch may contain at most 40 events.",
      413,
    );
  }

  const currentState = cloneJsonObject(
    input.currentState ?? {},
    "currentState",
    512 * 1024,
  );
  const events = input.events.map((event) =>
    sanitizeEvent(event, scope, now),
  );

  const seen = new Set<string>();
  for (const event of events) {
    if (seen.has(event.id)) {
      throw new ApiError(
        "DUPLICATE_EVENT_IN_BATCH",
        `Event ${event.id} appears more than once in this batch.`,
      );
    }
    seen.add(event.id);
  }

  const batch: SyncBatch = {
    schema: LEARNING_BATCH_SCHEMA,
    scope,
    events,
    currentState,
    baseCheckpointVersion:
      input.baseCheckpointVersion == null
        ? 0
        : Number(input.baseCheckpointVersion),
  };
  if (
    !Number.isSafeInteger(batch.baseCheckpointVersion) ||
    batch.baseCheckpointVersion < 0
  ) {
    throw new ApiError(
      "INVALID_INPUT",
      "baseCheckpointVersion must be a non-negative integer.",
    );
  }
  if (jsonByteLength(batch, "request") > 1024 * 1024) {
    throw new ApiError(
      "PAYLOAD_TOO_LARGE",
      "The sync request exceeds the 1 MiB limit.",
      413,
    );
  }
  return batch;
}

export function validateScoreAnswerInput(
  input: unknown,
): ScoreAnswerInput {
  assertRecord(input, "request");
  rejectClientIdentity(input, "request");
  for (const forbidden of [
    "task",
    "cue",
    "referenceAnswer",
    "canonicalAnswer",
    "acceptedAnswers",
    "intent",
    "meaningPatterns",
    "systemPrompt",
  ]) {
    if (Object.prototype.hasOwnProperty.call(input, forbidden)) {
      throw new ApiError(
        "CLIENT_RUBRIC_NOT_ALLOWED",
        `${forbidden} is loaded from the server rubric, not the client.`,
      );
    }
  }

  const result: ScoreAnswerInput = {
    assignmentId: requiredText(
      input.assignmentId,
      "assignmentId",
      180,
    ),
    sectionId: requiredText(input.sectionId, "sectionId", 180),
    itemId: requiredText(input.itemId, "itemId", 180),
    learnerAnswer: requiredText(
      input.learnerAnswer,
      "learnerAnswer",
      500,
    ),
    clientLocalVerdict: optionalText(input.clientLocalVerdict, 40),
  };

  if (
    result.clientLocalVerdict &&
    !["correct", "near_miss", "incorrect"].includes(
      result.clientLocalVerdict,
    )
  ) {
    throw new ApiError(
      "INVALID_INPUT",
      "clientLocalVerdict is not supported.",
    );
  }

  if (jsonByteLength(result, "request") > 24 * 1024) {
    throw new ApiError(
      "PAYLOAD_TOO_LARGE",
      "The score request is too large.",
      413,
    );
  }
  return result;
}
