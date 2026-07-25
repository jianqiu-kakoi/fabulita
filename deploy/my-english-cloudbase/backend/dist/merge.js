"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.EMPTY_TOMBSTONES = void 0;
exports.updateTombstones = updateTombstones;
exports.mergeCurrentState = mergeCurrentState;
const errors_1 = require("./errors");
const hash_1 = require("./hash");
exports.EMPTY_TOMBSTONES = {
    assignmentResetAt: {},
    questionDeletedAt: {},
};
function object(value) {
    return value != null && typeof value === "object" && !Array.isArray(value)
        ? value
        : {};
}
function array(value) {
    return Array.isArray(value) ? value : [];
}
function finiteTime(value) {
    const number = Number(value);
    return Number.isFinite(number) && number > 0 ? number : 0;
}
function newestTime(value, fields) {
    return fields.reduce((newest, field) => Math.max(newest, finiteTime(value[field])), 0);
}
function clone(value) {
    return JSON.parse(JSON.stringify(value));
}
function stableChoice(left, right) {
    const leftStable = (0, hash_1.stableStringify)(left);
    const rightStable = (0, hash_1.stableStringify)(right);
    return rightStable >= leftStable ? right : left;
}
function lww(leftValue, rightValue, timeFields = ["updatedAt", "checkedAt", "createdAt"]) {
    const left = object(leftValue);
    const right = object(rightValue);
    if (Object.keys(left).length === 0)
        return clone(right);
    if (Object.keys(right).length === 0)
        return clone(left);
    const leftTime = newestTime(left, timeFields);
    const rightTime = newestTime(right, timeFields);
    if (leftTime !== rightTime) {
        const winner = rightTime > leftTime ? right : left;
        const loser = winner === right ? left : right;
        return clone({ ...loser, ...winner });
    }
    return clone(stableChoice(left, right));
}
function mapById(values, idField) {
    const result = new Map();
    for (const raw of array(values)) {
        const item = object(raw);
        const id = typeof item[idField] === "string" ? item[idField] : "";
        if (!id)
            continue;
        const previous = result.get(id);
        result.set(id, previous ? lww(previous, item) : clone(item));
    }
    return result;
}
function mergeResponseMaps(leftValue, rightValue, resetAt) {
    const left = object(leftValue);
    const right = object(rightValue);
    const ids = new Set([...Object.keys(left), ...Object.keys(right)]);
    const merged = {};
    for (const id of ids) {
        const response = lww(left[id], right[id], [
            "updatedAt",
            "checkedAt",
            "ratedAt",
            "studiedAt",
        ]);
        if (resetAt &&
            newestTime(response, [
                "updatedAt",
                "checkedAt",
                "ratedAt",
                "studiedAt",
            ]) <= resetAt) {
            continue;
        }
        merged[id] = response;
    }
    return merged;
}
function mergeAssignment(assignmentId, leftValue, rightValue, resetAt) {
    const left = object(leftValue);
    const right = object(rightValue);
    const newer = lww(left, right, ["updatedAt"]);
    const merged = {
        ...left,
        ...right,
        ...newer,
        responses: mergeResponseMaps(left.responses, right.responses, resetAt),
        updatedAt: Math.max(finiteTime(left.updatedAt), finiteTime(right.updatedAt), resetAt),
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
    const completedAt = Math.max(finiteTime(left.completedAt), finiteTime(right.completedAt));
    merged.completedAt = completedAt > resetAt ? completedAt : null;
    if (resetAt)
        merged.resetAt = resetAt;
    merged.assignmentId = assignmentId;
    return merged;
}
function mergeAssignmentScope(leftValue, rightValue, tombstones) {
    const left = object(leftValue);
    const right = object(rightValue);
    const leftAssignments = object(left.assignments);
    const rightAssignments = object(right.assignments);
    const ids = new Set([
        ...Object.keys(leftAssignments),
        ...Object.keys(rightAssignments),
        ...Object.keys(tombstones.assignmentResetAt),
    ]);
    const assignments = {};
    for (const id of ids) {
        assignments[id] = mergeAssignment(id, leftAssignments[id], rightAssignments[id], tombstones.assignmentResetAt[id] || 0);
    }
    return {
        ...left,
        ...right,
        assignments,
        updatedAt: Math.max(finiteTime(left.updatedAt), finiteTime(right.updatedAt), ...Object.values(tombstones.assignmentResetAt)),
    };
}
function mergeReviewCard(leftValue, rightValue) {
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
    const scheduleWinner = leftScheduleAt === rightScheduleAt
        ? stableChoice(left, right)
        : rightScheduleAt > leftScheduleAt
            ? right
            : left;
    const scheduleLoser = scheduleWinner === right ? left : right;
    const merged = {
        ...scheduleLoser,
        ...scheduleWinner,
        reviews: Math.max(Number(left.reviews) || 0, Number(right.reviews) || 0),
        lapses: Math.max(Number(left.lapses) || 0, Number(right.lapses) || 0),
    };
    const leftFavoriteAt = finiteTime(left.favoriteUpdatedAt);
    const rightFavoriteAt = finiteTime(right.favoriteUpdatedAt);
    if (leftFavoriteAt || rightFavoriteAt) {
        const favoriteWinner = rightFavoriteAt >= leftFavoriteAt ? right : left;
        merged.favorite = favoriteWinner.favorite === true;
        merged.favoriteUpdatedAt = Math.max(leftFavoriteAt, rightFavoriteAt);
    }
    else {
        merged.favorite = left.favorite === true || right.favorite === true;
    }
    return clone(merged);
}
function mergeReviewScope(leftValue, rightValue) {
    const left = object(leftValue);
    const right = object(rightValue);
    const leftCards = object(left.cards);
    const rightCards = object(right.cards);
    const keys = new Set([
        ...Object.keys(leftCards),
        ...Object.keys(rightCards),
    ]);
    const cards = {};
    for (const key of keys) {
        cards[key] = mergeReviewCard(leftCards[key], rightCards[key]);
    }
    return {
        ...left,
        ...right,
        cards,
        active: null,
        updatedAt: Math.max(finiteTime(left.updatedAt), finiteTime(right.updatedAt)),
    };
}
function mergeQaItems(leftValue, rightValue, tombstones) {
    const left = mapById(leftValue, "id");
    const right = mapById(rightValue, "id");
    const ids = new Set([...left.keys(), ...right.keys()]);
    const merged = [];
    for (const id of ids) {
        if (tombstones.questionDeletedAt[id])
            continue;
        merged.push(lww(left.get(id), right.get(id), [
            "updatedAt",
            "createdAt",
        ]));
    }
    return merged.sort((a, b) => finiteTime(b.createdAt) - finiteTime(a.createdAt));
}
function mergeQaScope(leftValue, rightValue, tombstones) {
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
        updatedAt: Math.max(finiteTime(left.updatedAt), finiteTime(right.updatedAt), ...Object.values(tombstones.questionDeletedAt)),
    };
}
function mergeAppendOnlyEvents(leftValue, rightValue) {
    const left = object(leftValue);
    const right = object(rightValue);
    const byId = mapById([...array(left.events), ...array(right.events)], "id");
    return {
        ...left,
        ...right,
        events: [...byId.values()].sort((a, b) => newestTime(b, ["reviewedAt", "occurredAt"]) -
            newestTime(a, ["reviewedAt", "occurredAt"])),
        updatedAt: Math.max(finiteTime(left.updatedAt), finiteTime(right.updatedAt)),
    };
}
function mergeRawScopes(leftValue, rightValue, tombstones) {
    const left = object(leftValue);
    const right = object(rightValue);
    const result = {};
    const keys = new Set([...Object.keys(left), ...Object.keys(right)]);
    for (const key of keys) {
        if (key === "review") {
            result[key] = mergeReviewScope(left[key], right[key]);
        }
        else if (key === "homework" || key === "homeworkStudy") {
            result[key] = mergeAssignmentScope(left[key], right[key], tombstones);
        }
        else if (key === "qa") {
            result[key] = mergeQaScope(left[key], right[key], tombstones);
        }
        else if (key === "reviewEvents") {
            result[key] = mergeAppendOnlyEvents(left[key], right[key]);
        }
        else {
            result[key] = lww(left[key], right[key]);
        }
    }
    return result;
}
function mergeReviewCards(leftValue, rightValue) {
    const left = mapById(leftValue, "wordKey");
    const right = mapById(rightValue, "wordKey");
    const ids = new Set([...left.keys(), ...right.keys()]);
    return [...ids].map((id) => mergeReviewCard(left.get(id), right.get(id)));
}
function mergeHomeworkSummaryAssignment(leftValue, rightValue, resetAt) {
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
        completedAt: Math.max(finiteTime(leftStudy.completedAt), finiteTime(rightStudy.completedAt)) > resetAt
            ? Math.max(finiteTime(leftStudy.completedAt), finiteTime(rightStudy.completedAt))
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
    const completedAt = Math.max(finiteTime(left.completedAt), finiteTime(right.completedAt));
    merged.completedAt = completedAt > resetAt ? completedAt : null;
    return merged;
}
function mergeHomeworkSummaries(leftValue, rightValue, tombstones) {
    const left = mapById(leftValue, "assignmentId");
    const right = mapById(rightValue, "assignmentId");
    const ids = new Set([
        ...left.keys(),
        ...right.keys(),
        ...Object.keys(tombstones.assignmentResetAt),
    ]);
    return [...ids].map((id) => mergeHomeworkSummaryAssignment(left.get(id), right.get(id), tombstones.assignmentResetAt[id] || 0));
}
function updateTombstones(current, events) {
    const next = clone(current || exports.EMPTY_TOMBSTONES);
    for (const event of events) {
        if (event.source === "homework" && event.action === "assignment_reset") {
            const assignmentId = event.assignmentId || event.entityId;
            if (assignmentId) {
                next.assignmentResetAt[assignmentId] = Math.max(next.assignmentResetAt[assignmentId] || 0, event.occurredAt);
            }
        }
        if (event.source === "qa" && event.action === "question_deleted") {
            if (event.entityId) {
                next.questionDeletedAt[event.entityId] = Math.max(next.questionDeletedAt[event.entityId] || 0, event.occurredAt);
            }
        }
    }
    return next;
}
function mergeCurrentState(existingValue, incomingValue, tombstones) {
    const existing = object(existingValue);
    const incoming = object(incomingValue);
    const existingRaw = object(existing.rawScopes);
    const incomingRaw = object(incoming.rawScopes);
    const rawScopes = mergeRawScopes(existingRaw, incomingRaw, tombstones);
    const qaScope = object(rawScopes.qa);
    const qa = Array.isArray(qaScope.items)
        ? clone(qaScope.items)
        : mergeQaItems(existing.qa, incoming.qa, tombstones);
    const merged = {
        ...clone(existing),
        ...clone(incoming),
        reviewCards: mergeReviewCards(existing.reviewCards, incoming.reviewCards),
        homework: mergeHomeworkSummaries(existing.homework, incoming.homework, tombstones),
        qa: qa,
        rawScopes,
    };
    const byteLength = new TextEncoder().encode(JSON.stringify(merged)).byteLength;
    if (byteLength > 1024 * 1024) {
        throw new errors_1.ApiError("CHECKPOINT_TOO_LARGE", "The merged learning checkpoint exceeds the 1 MiB limit.", 413);
    }
    return merged;
}
