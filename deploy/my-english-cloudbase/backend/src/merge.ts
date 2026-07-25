import type { JsonObject, JsonValue, LearningEvent } from "./contracts";
import { ApiError } from "./errors";
import { stableStringify } from "./hash";

type PlainObject = Record<string, unknown>;

export interface SyncTombstones {
  assignmentResetAt: Record<string, number>;
  questionDeletedAt: Record<string, number>;
}

export const EMPTY_TOMBSTONES: SyncTombstones = {
  assignmentResetAt: {},
  questionDeletedAt: {},
};

function object(value: unknown): PlainObject {
  return value != null && typeof value === "object" && !Array.isArray(value)
    ? (value as PlainObject)
    : {};
}

function array(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function finiteTime(value: unknown): number {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? number : 0;
}

function newestTime(
  value: PlainObject,
  fields: readonly string[],
): number {
  return fields.reduce(
    (newest, field) => Math.max(newest, finiteTime(value[field])),
    0,
  );
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function stableChoice(
  left: PlainObject,
  right: PlainObject,
): PlainObject {
  const leftStable = stableStringify(left as JsonValue);
  const rightStable = stableStringify(right as JsonValue);
  return rightStable >= leftStable ? right : left;
}

function lww(
  leftValue: unknown,
  rightValue: unknown,
  timeFields = ["updatedAt", "checkedAt", "createdAt"],
): PlainObject {
  const left = object(leftValue);
  const right = object(rightValue);
  if (Object.keys(left).length === 0) return clone(right);
  if (Object.keys(right).length === 0) return clone(left);
  const leftTime = newestTime(left, timeFields);
  const rightTime = newestTime(right, timeFields);
  if (leftTime !== rightTime) {
    const winner = rightTime > leftTime ? right : left;
    const loser = winner === right ? left : right;
    return clone({ ...loser, ...winner });
  }
  return clone(stableChoice(left, right));
}

function mapById(
  values: unknown,
  idField: string,
): Map<string, PlainObject> {
  const result = new Map<string, PlainObject>();
  for (const raw of array(values)) {
    const item = object(raw);
    const id = typeof item[idField] === "string" ? item[idField] : "";
    if (!id) continue;
    const previous = result.get(id);
    result.set(id, previous ? lww(previous, item) : clone(item));
  }
  return result;
}

function mergeResponseMaps(
  leftValue: unknown,
  rightValue: unknown,
  resetAt: number,
): PlainObject {
  const left = object(leftValue);
  const right = object(rightValue);
  const ids = new Set([...Object.keys(left), ...Object.keys(right)]);
  const merged: PlainObject = {};
  for (const id of ids) {
    const response = lww(left[id], right[id], [
      "updatedAt",
      "checkedAt",
      "ratedAt",
      "studiedAt",
    ]);
    if (
      resetAt &&
      newestTime(response, [
        "updatedAt",
        "checkedAt",
        "ratedAt",
        "studiedAt",
      ]) <= resetAt
    ) {
      continue;
    }
    merged[id] = response;
  }
  return merged;
}

function mergeAssignment(
  assignmentId: string,
  leftValue: unknown,
  rightValue: unknown,
  resetAt: number,
): PlainObject {
  const left = object(leftValue);
  const right = object(rightValue);
  const newer = lww(left, right, ["updatedAt"]);
  const merged: PlainObject = {
    ...left,
    ...right,
    ...newer,
    responses: mergeResponseMaps(
      left.responses,
      right.responses,
      resetAt,
    ),
    updatedAt: Math.max(
      finiteTime(left.updatedAt),
      finiteTime(right.updatedAt),
      resetAt,
    ),
  };

  const leftUpdatedAt = finiteTime(left.updatedAt);
  const rightUpdatedAt = finiteTime(right.updatedAt);
  const navigationWinner = rightUpdatedAt >= leftUpdatedAt ? right : left;
  if (typeof navigationWinner.currentItemId === "string") {
    merged.currentItemId = navigationWinner.currentItemId;
  }
  if (typeof navigationWinner.currentWordId === "string") {
    merged.currentWordId = navigationWinner.currentWordId;
  }
  if (typeof navigationWinner.lastTab === "string") {
    merged.lastTab = navigationWinner.lastTab;
  }

  const completedAt = Math.max(
    finiteTime(left.completedAt),
    finiteTime(right.completedAt),
  );
  merged.completedAt = completedAt > resetAt ? completedAt : null;
  if (resetAt) merged.resetAt = resetAt;
  merged.assignmentId = assignmentId;
  return merged;
}

function mergeAssignmentScope(
  leftValue: unknown,
  rightValue: unknown,
  tombstones: SyncTombstones,
): JsonValue {
  const left = object(leftValue);
  const right = object(rightValue);
  const leftAssignments = object(left.assignments);
  const rightAssignments = object(right.assignments);
  const ids = new Set([
    ...Object.keys(leftAssignments),
    ...Object.keys(rightAssignments),
    ...Object.keys(tombstones.assignmentResetAt),
  ]);
  const assignments: PlainObject = {};
  for (const id of ids) {
    assignments[id] = mergeAssignment(
      id,
      leftAssignments[id],
      rightAssignments[id],
      tombstones.assignmentResetAt[id] || 0,
    );
  }
  return {
    ...left,
    ...right,
    assignments,
    updatedAt: Math.max(
      finiteTime(left.updatedAt),
      finiteTime(right.updatedAt),
      ...Object.values(tombstones.assignmentResetAt),
    ),
  } as JsonValue;
}

function mergeReviewCard(
  leftValue: unknown,
  rightValue: unknown,
): PlainObject {
  const left = object(leftValue);
  const right = object(rightValue);
  const leftScheduleAt = newestTime(left, [
    "lastReviewedAt",
    "updatedAt",
    "homeworkQueuedAt",
    "dueAt",
  ]);
  const rightScheduleAt = newestTime(right, [
    "lastReviewedAt",
    "updatedAt",
    "homeworkQueuedAt",
    "dueAt",
  ]);
  const scheduleWinner =
    leftScheduleAt === rightScheduleAt
      ? stableChoice(left, right)
      : rightScheduleAt > leftScheduleAt
        ? right
        : left;
  const scheduleLoser = scheduleWinner === right ? left : right;
  const merged: PlainObject = {
    ...scheduleLoser,
    ...scheduleWinner,
    reviews: Math.max(
      Number(left.reviews) || 0,
      Number(right.reviews) || 0,
    ),
    lapses: Math.max(
      Number(left.lapses) || 0,
      Number(right.lapses) || 0,
    ),
  };

  const leftFavoriteAt = finiteTime(left.favoriteUpdatedAt);
  const rightFavoriteAt = finiteTime(right.favoriteUpdatedAt);
  if (leftFavoriteAt || rightFavoriteAt) {
    const favoriteWinner =
      rightFavoriteAt >= leftFavoriteAt ? right : left;
    merged.favorite = favoriteWinner.favorite === true;
    merged.favoriteUpdatedAt = Math.max(
      leftFavoriteAt,
      rightFavoriteAt,
    );
  } else {
    merged.favorite = left.favorite === true || right.favorite === true;
  }
  return clone(merged);
}

function mergeReviewScope(
  leftValue: unknown,
  rightValue: unknown,
): JsonValue {
  const left = object(leftValue);
  const right = object(rightValue);
  const leftCards = object(left.cards);
  const rightCards = object(right.cards);
  const keys = new Set([
    ...Object.keys(leftCards),
    ...Object.keys(rightCards),
  ]);
  const cards: PlainObject = {};
  for (const key of keys) {
    cards[key] = mergeReviewCard(leftCards[key], rightCards[key]);
  }
  return {
    ...left,
    ...right,
    cards,
    active: null,
    updatedAt: Math.max(
      finiteTime(left.updatedAt),
      finiteTime(right.updatedAt),
    ),
  } as JsonValue;
}

function mergeQaItems(
  leftValue: unknown,
  rightValue: unknown,
  tombstones: SyncTombstones,
): PlainObject[] {
  const left = mapById(leftValue, "id");
  const right = mapById(rightValue, "id");
  const ids = new Set([...left.keys(), ...right.keys()]);
  const merged: PlainObject[] = [];
  for (const id of ids) {
    if (tombstones.questionDeletedAt[id]) continue;
    merged.push(lww(left.get(id), right.get(id), [
      "updatedAt",
      "createdAt",
    ]));
  }
  return merged.sort(
    (a, b) => finiteTime(b.createdAt) - finiteTime(a.createdAt),
  );
}

function mergeQaScope(
  leftValue: unknown,
  rightValue: unknown,
  tombstones: SyncTombstones,
): JsonValue {
  const left = object(leftValue);
  const right = object(rightValue);
  return {
    ...left,
    ...right,
    items: mergeQaItems(left.items, right.items, tombstones),
    tombstones: {
      ...object(left.tombstones),
      ...object(right.tombstones),
      ...tombstones.questionDeletedAt,
    },
    updatedAt: Math.max(
      finiteTime(left.updatedAt),
      finiteTime(right.updatedAt),
      ...Object.values(tombstones.questionDeletedAt),
    ),
  } as JsonValue;
}

function mergeAppendOnlyEvents(
  leftValue: unknown,
  rightValue: unknown,
): JsonValue {
  const left = object(leftValue);
  const right = object(rightValue);
  const byId = mapById(
    [...array(left.events), ...array(right.events)],
    "id",
  );
  return {
    ...left,
    ...right,
    events: [...byId.values()].sort(
      (a, b) =>
        newestTime(b, ["reviewedAt", "occurredAt"]) -
        newestTime(a, ["reviewedAt", "occurredAt"]),
    ),
    updatedAt: Math.max(
      finiteTime(left.updatedAt),
      finiteTime(right.updatedAt),
    ),
  } as JsonValue;
}

function mergeRawScopes(
  leftValue: unknown,
  rightValue: unknown,
  tombstones: SyncTombstones,
): JsonObject {
  const left = object(leftValue);
  const right = object(rightValue);
  const result: JsonObject = {};
  const keys = new Set([...Object.keys(left), ...Object.keys(right)]);
  for (const key of keys) {
    if (key === "review") {
      result[key] = mergeReviewScope(left[key], right[key]);
    } else if (key === "homework" || key === "homeworkStudy") {
      result[key] = mergeAssignmentScope(
        left[key],
        right[key],
        tombstones,
      );
    } else if (key === "qa") {
      result[key] = mergeQaScope(left[key], right[key], tombstones);
    } else if (key === "reviewEvents") {
      result[key] = mergeAppendOnlyEvents(left[key], right[key]);
    } else {
      result[key] = lww(left[key], right[key]) as JsonValue;
    }
  }
  return result;
}

function mergeReviewCards(
  leftValue: unknown,
  rightValue: unknown,
): JsonValue[] {
  const left = mapById(leftValue, "wordKey");
  const right = mapById(rightValue, "wordKey");
  const ids = new Set([...left.keys(), ...right.keys()]);
  return [...ids].map((id) =>
    mergeReviewCard(left.get(id), right.get(id)),
  ) as JsonValue[];
}

function mergeHomeworkSummaryAssignment(
  leftValue: unknown,
  rightValue: unknown,
  resetAt: number,
): PlainObject {
  const left = object(leftValue);
  const right = object(rightValue);
  const merged = lww(left, right, ["completedAt"]);

  const leftItems = mapById(left.items, "itemId");
  const rightItems = mapById(right.items, "itemId");
  const itemIds = new Set([...leftItems.keys(), ...rightItems.keys()]);
  merged.items = [...itemIds].map((id) => {
    const leftItem = object(leftItems.get(id));
    const rightItem = object(rightItems.get(id));
    return {
      ...leftItem,
      ...rightItem,
      response: (() => {
        const response = lww(leftItem.response, rightItem.response, [
          "updatedAt",
          "checkedAt",
        ]);
        return newestTime(response, ["updatedAt", "checkedAt"]) > resetAt
          ? response
          : null;
      })(),
    };
  });

  const leftStudy = object(left.study);
  const rightStudy = object(right.study);
  const leftWords = mapById(leftStudy.words, "wordId");
  const rightWords = mapById(rightStudy.words, "wordId");
  const wordIds = new Set([...leftWords.keys(), ...rightWords.keys()]);
  merged.study = {
    ...leftStudy,
    ...rightStudy,
    completedAt:
      Math.max(
        finiteTime(leftStudy.completedAt),
        finiteTime(rightStudy.completedAt),
      ) > resetAt
        ? Math.max(
            finiteTime(leftStudy.completedAt),
            finiteTime(rightStudy.completedAt),
          )
        : null,
    words: [...wordIds].map((id) => {
      const leftWord = object(leftWords.get(id));
      const rightWord = object(rightWords.get(id));
      return {
        ...leftWord,
        ...rightWord,
        response: (() => {
          const response = lww(leftWord.response, rightWord.response, [
            "updatedAt",
            "checkedAt",
            "ratedAt",
            "studiedAt",
          ]);
          return newestTime(response, [
            "updatedAt",
            "checkedAt",
            "ratedAt",
            "studiedAt",
          ]) > resetAt
            ? response
            : null;
        })(),
      };
    }),
  };
  const completedAt = Math.max(
    finiteTime(left.completedAt),
    finiteTime(right.completedAt),
  );
  merged.completedAt = completedAt > resetAt ? completedAt : null;
  return merged;
}

function mergeHomeworkSummaries(
  leftValue: unknown,
  rightValue: unknown,
  tombstones: SyncTombstones,
): JsonValue[] {
  const left = mapById(leftValue, "assignmentId");
  const right = mapById(rightValue, "assignmentId");
  const ids = new Set([
    ...left.keys(),
    ...right.keys(),
    ...Object.keys(tombstones.assignmentResetAt),
  ]);
  return [...ids].map((id) =>
    mergeHomeworkSummaryAssignment(
      left.get(id),
      right.get(id),
      tombstones.assignmentResetAt[id] || 0,
    ),
  ) as JsonValue[];
}

export function updateTombstones(
  current: SyncTombstones | undefined,
  events: LearningEvent[],
): SyncTombstones {
  const next: SyncTombstones = clone(current || EMPTY_TOMBSTONES);
  for (const event of events) {
    if (event.source === "homework" && event.action === "assignment_reset") {
      const assignmentId = event.assignmentId || event.entityId;
      if (assignmentId) {
        next.assignmentResetAt[assignmentId] = Math.max(
          next.assignmentResetAt[assignmentId] || 0,
          event.occurredAt,
        );
      }
    }
    if (event.source === "qa" && event.action === "question_deleted") {
      if (event.entityId) {
        next.questionDeletedAt[event.entityId] = Math.max(
          next.questionDeletedAt[event.entityId] || 0,
          event.occurredAt,
        );
      }
    }
  }
  return next;
}

export function mergeCurrentState(
  existingValue: JsonObject | undefined,
  incomingValue: JsonObject,
  tombstones: SyncTombstones,
): JsonObject {
  const existing = object(existingValue);
  const incoming = object(incomingValue);
  const existingRaw = object(existing.rawScopes);
  const incomingRaw = object(incoming.rawScopes);
  const rawScopes = mergeRawScopes(
    existingRaw,
    incomingRaw,
    tombstones,
  );

  const qaScope = object(rawScopes.qa);
  const qa = Array.isArray(qaScope.items)
    ? clone(qaScope.items)
    : mergeQaItems(existing.qa, incoming.qa, tombstones);

  const merged: JsonObject = {
    ...(clone(existing) as JsonObject),
    ...(clone(incoming) as JsonObject),
    reviewCards: mergeReviewCards(
      existing.reviewCards,
      incoming.reviewCards,
    ),
    homework: mergeHomeworkSummaries(
      existing.homework,
      incoming.homework,
      tombstones,
    ),
    qa: qa as JsonValue,
    rawScopes,
  };

  const byteLength = new TextEncoder().encode(
    JSON.stringify(merged),
  ).byteLength;
  if (byteLength > 1024 * 1024) {
    throw new ApiError(
      "CHECKPOINT_TOO_LARGE",
      "The merged learning checkpoint exceeds the 1 MiB limit.",
      413,
    );
  }
  return merged;
}
