"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.CLOUD_DATABASE_COLLECTIONS = exports.CloudBaseLearningStore = void 0;
exports.parseCursor = parseCursor;
const errors_1 = require("./errors");
const hash_1 = require("./hash");
const merge_1 = require("./merge");
const EVENTS_COLLECTION = "learning_events";
const CHECKPOINTS_COLLECTION = "learning_checkpoints";
const RATE_LIMITS_COLLECTION = "learning_rate_limits";
function firstDocument(result) {
    const data = result && result.data;
    if (Array.isArray(data))
        return data[0];
    if (data && typeof data === "object")
        return data;
    return undefined;
}
async function unwrapTransaction(promise) {
    const value = await promise;
    if (value != null &&
        typeof value === "object" &&
        "result" in value) {
        return value.result;
    }
    return value;
}
function cursorFor(version, eventSequence) {
    return `c:${version}:${eventSequence}`;
}
function parseCursor(cursor) {
    if (!cursor)
        return { checkpointVersion: 0, eventSequence: 0 };
    const match = /^c:(\d+):(\d+)$/.exec(cursor);
    if (!match) {
        throw new errors_1.ApiError("INVALID_CURSOR", "cursor has an invalid format.");
    }
    const checkpointVersion = Number(match[1]);
    const eventSequence = Number(match[2]);
    if (!Number.isSafeInteger(checkpointVersion) ||
        !Number.isSafeInteger(eventSequence)) {
        throw new errors_1.ApiError("INVALID_CURSOR", "cursor is outside valid bounds.");
    }
    return { checkpointVersion, eventSequence };
}
function checkpointFromDocument(raw, ownerKey, scope) {
    if (!raw) {
        return {
            ownerKey,
            scope,
            version: 0,
            lastEventSequence: 0,
            currentState: {},
            stateHash: (0, hash_1.stableStringify)({}),
            updatedAt: 0,
            tombstones: {
                assignmentResetAt: {},
                questionDeletedAt: {},
            },
        };
    }
    return {
        ownerKey,
        scope,
        version: Number(raw.version) || 0,
        lastEventSequence: Number(raw.lastEventSequence) || 0,
        currentState: raw.currentState &&
            typeof raw.currentState === "object" &&
            !Array.isArray(raw.currentState)
            ? raw.currentState
            : {},
        stateHash: typeof raw.stateHash === "string"
            ? raw.stateHash
            : (0, hash_1.stableStringify)(raw.currentState || {}),
        updatedAt: Number(raw.updatedAt) || 0,
        tombstones: raw.tombstones || merge_1.EMPTY_TOMBSTONES,
    };
}
class CloudBaseLearningStore {
    database;
    constructor(database) {
        this.database = database;
    }
    async syncBatch(ownerKey, batch, now) {
        const checkpointId = (0, hash_1.checkpointDocumentId)(ownerKey, batch.scope);
        return unwrapTransaction(this.database.runTransaction(async (transaction) => {
            const checkpointReference = transaction
                .collection(CHECKPOINTS_COLLECTION)
                .doc(checkpointId);
            const checkpointResult = await checkpointReference.get();
            const current = checkpointFromDocument(firstDocument(checkpointResult), ownerKey, batch.scope);
            if (batch.baseCheckpointVersion > current.version) {
                throw new errors_1.ApiError("CHECKPOINT_AHEAD", "baseCheckpointVersion is newer than the server checkpoint.", 409);
            }
            const newEvents = [];
            for (const event of batch.events) {
                const eventHash = (0, hash_1.sha256)((0, hash_1.stableStringify)(event));
                const reference = transaction
                    .collection(EVENTS_COLLECTION)
                    .doc((0, hash_1.eventDocumentId)(ownerKey, event.id));
                const existing = firstDocument(await reference.get());
                if (existing) {
                    if (existing.ownerKey !== ownerKey ||
                        existing.eventId !== event.id ||
                        existing.eventHash !== eventHash) {
                        throw new errors_1.ApiError("EVENT_ID_CONFLICT", `Event ${event.id} is immutable and already has different content.`, 409);
                    }
                }
                else {
                    newEvents.push({ reference, event, hash: eventHash });
                }
            }
            const tombstones = (0, merge_1.updateTombstones)(current.tombstones, batch.events);
            const mergedState = (0, merge_1.mergeCurrentState)(current.currentState, batch.currentState, tombstones);
            const stateHash = (0, hash_1.sha256)((0, hash_1.stableStringify)(mergedState));
            const tombstoneHash = (0, hash_1.sha256)((0, hash_1.stableStringify)(tombstones));
            const previousTombstoneHash = (0, hash_1.sha256)((0, hash_1.stableStringify)(current.tombstones));
            const checkpointChanged = newEvents.length > 0 ||
                stateHash !== current.stateHash ||
                tombstoneHash !== previousTombstoneHash ||
                current.version === 0;
            const version = checkpointChanged
                ? current.version + 1
                : current.version;
            let nextSequence = current.lastEventSequence;
            for (const entry of newEvents) {
                nextSequence += 1;
                const record = {
                    ownerKey,
                    scope: batch.scope,
                    eventId: entry.event.id,
                    eventHash: entry.hash,
                    sequence: nextSequence,
                    receivedAt: now,
                    payload: entry.event,
                };
                await entry.reference.set(record);
            }
            const checkpointUpdatedAt = checkpointChanged
                ? now
                : current.updatedAt;
            if (checkpointChanged) {
                const checkpoint = {
                    ownerKey,
                    scope: batch.scope,
                    version,
                    lastEventSequence: nextSequence,
                    currentState: mergedState,
                    stateHash,
                    updatedAt: checkpointUpdatedAt,
                    tombstones,
                };
                await checkpointReference.set(checkpoint);
            }
            return {
                acknowledgedEventIds: batch.events.map((event) => event.id),
                cursor: cursorFor(version, nextSequence),
                checkpointUpdatedAt,
                checkpointVersion: version,
            };
        }));
    }
    async bootstrap(ownerKey, scope, cursor, requestedLimit = 200) {
        const parsedCursor = parseCursor(cursor);
        const checkpointResult = await this.database
            .collection(CHECKPOINTS_COLLECTION)
            .doc((0, hash_1.checkpointDocumentId)(ownerKey, scope))
            .get();
        const checkpoint = checkpointFromDocument(firstDocument(checkpointResult), ownerKey, scope);
        if (parsedCursor.checkpointVersion > checkpoint.version ||
            parsedCursor.eventSequence > checkpoint.lastEventSequence) {
            throw new errors_1.ApiError("INVALID_CURSOR", "cursor is ahead of the server checkpoint.", 409);
        }
        const limit = Math.max(1, Math.min(200, requestedLimit));
        const queryResult = await this.database
            .collection(EVENTS_COLLECTION)
            .where({
            ownerKey,
            scope,
            sequence: this.database.command.gt(parsedCursor.eventSequence),
        })
            .orderBy("sequence", "asc")
            .limit(limit + 1)
            .get();
        const records = Array.isArray(queryResult.data)
            ? queryResult.data
            : [];
        const hasMore = records.length > limit;
        const page = records.slice(0, limit);
        const eventSequence = page.length > 0
            ? Number(page[page.length - 1].sequence) ||
                parsedCursor.eventSequence
            : parsedCursor.eventSequence;
        return {
            scope,
            cursor: cursorFor(checkpoint.version, eventSequence),
            checkpoint: {
                currentState: checkpoint.currentState,
                updatedAt: checkpoint.updatedAt,
                version: checkpoint.version,
            },
            events: page.map((record) => record.payload),
            hasMore,
        };
    }
    async consumeScoreLimit(ownerKey, now, limit) {
        const windowStartedAt = Math.floor(now / 60_000) * 60_000;
        const retryAfterMs = windowStartedAt + 60_000 - now;
        const documentId = (0, hash_1.rateLimitDocumentId)(ownerKey);
        return unwrapTransaction(this.database.runTransaction(async (transaction) => {
            const reference = transaction
                .collection(RATE_LIMITS_COLLECTION)
                .doc(documentId);
            const previous = firstDocument(await reference.get());
            const previousCount = previous?.windowStartedAt === windowStartedAt
                ? Number(previous.count) || 0
                : 0;
            if (previousCount >= limit) {
                return { allowed: false, retryAfterMs };
            }
            await reference.set({
                ownerKey,
                windowStartedAt,
                count: previousCount + 1,
                expiresAt: windowStartedAt + 2 * 60_000,
            });
            return { allowed: true, retryAfterMs };
        }));
    }
}
exports.CloudBaseLearningStore = CloudBaseLearningStore;
exports.CLOUD_DATABASE_COLLECTIONS = {
    events: EVENTS_COLLECTION,
    checkpoints: CHECKPOINTS_COLLECTION,
    rateLimits: RATE_LIMITS_COLLECTION,
};
