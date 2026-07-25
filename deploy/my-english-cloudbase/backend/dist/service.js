"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.createBackendService = createBackendService;
const contracts_1 = require("./contracts");
const errors_1 = require("./errors");
const hash_1 = require("./hash");
const rubrics_1 = require("./rubrics");
const CLIENT_IDENTITY_FIELDS = [
    "userId",
    "uid",
    "owner",
    "ownerId",
    "ownerKey",
    "openId",
    "customUserId",
];
function requestObject(value) {
    if (value == null || typeof value !== "object" || Array.isArray(value)) {
        throw new errors_1.ApiError("INVALID_INPUT", "request must be an object.");
    }
    const request = value;
    for (const field of CLIENT_IDENTITY_FIELDS) {
        if (Object.prototype.hasOwnProperty.call(request, field)) {
            throw new errors_1.ApiError("CLIENT_IDENTITY_NOT_ALLOWED", `${field} is not accepted; identity comes from CloudBase auth.`);
        }
    }
    return request;
}
function optionalCursor(value) {
    if (value == null || value === "")
        return "";
    if (typeof value !== "string" || value.length > 100) {
        throw new errors_1.ApiError("INVALID_CURSOR", "cursor is invalid.");
    }
    return value;
}
async function authenticatedOwnerKey(getTrustedUid) {
    const uid = await getTrustedUid();
    if (typeof uid !== "string" || !uid.trim()) {
        throw new errors_1.ApiError("AUTHENTICATION_REQUIRED", "Sign in before using cloud learning data.", 401);
    }
    return (0, hash_1.ownerKeyFromUid)(uid.trim());
}
function createBackendService(dependencies) {
    const now = dependencies.now || Date.now;
    const scoreLimit = Math.max(1, Math.min(60, dependencies.scoreLimitPerMinute || 10));
    return {
        async handle(value) {
            const request = requestObject(value);
            const action = request.action;
            if (action === "health") {
                return {
                    ok: true,
                    service: "my-english-api",
                    version: "0.1.0",
                    serverTime: new Date(now()).toISOString(),
                };
            }
            if (action !== "syncBatch" &&
                action !== "bootstrap" &&
                action !== "scoreAnswer") {
                throw new errors_1.ApiError("UNKNOWN_ACTION", "action must be health, syncBatch, bootstrap, or scoreAnswer.", 404);
            }
            const ownerKey = await authenticatedOwnerKey(dependencies.getTrustedUid);
            if (action === "syncBatch") {
                const batchInput = request.batch != null &&
                    typeof request.batch === "object" &&
                    !Array.isArray(request.batch)
                    ? request.batch
                    : request;
                const batch = (0, contracts_1.validateSyncBatch)(batchInput, now());
                const result = await dependencies.store.syncBatch(ownerKey, batch, now());
                return {
                    ok: true,
                    acknowledgedEventIds: result.acknowledgedEventIds,
                    cursor: result.cursor,
                    checkpointUpdatedAt: result.checkpointUpdatedAt,
                    checkpointVersion: result.checkpointVersion,
                };
            }
            if (action === "bootstrap") {
                const scope = (0, contracts_1.validateScope)(request.scope);
                const cursor = optionalCursor(request.cursor);
                const result = await dependencies.store.bootstrap(ownerKey, scope, cursor);
                return {
                    ok: true,
                    scope: result.scope,
                    cursor: result.cursor,
                    checkpoint: result.checkpoint,
                    events: result.events,
                    hasMore: result.hasMore,
                    checkpointVersion: result.checkpoint.version,
                };
            }
            const scoreInput = request.payload != null &&
                typeof request.payload === "object" &&
                !Array.isArray(request.payload)
                ? request.payload
                : request;
            const input = (0, contracts_1.validateScoreAnswerInput)(scoreInput);
            const rubric = (0, rubrics_1.findScoringRubric)(input.assignmentId, input.sectionId, input.itemId);
            const rateLimit = await dependencies.store.consumeScoreLimit(ownerKey, now(), scoreLimit);
            if (!rateLimit.allowed) {
                throw new errors_1.ApiError("RATE_LIMITED", "Too many scoring requests. Please try again shortly.", 429, rateLimit.retryAfterMs);
            }
            const score = await dependencies.scorer.score(input, rubric);
            return {
                ok: true,
                verdict: score.verdict,
                meaningCorrect: score.meaningCorrect,
                feedbackZh: score.feedbackZh,
                suggestedAnswer: score.suggestedAnswer,
                scoringSource: "llm",
                confidence: score.confidence,
                issues: score.issues,
                modelVersion: score.modelVersion,
                rubricVersion: rubric.rubricVersion,
            };
        },
    };
}
