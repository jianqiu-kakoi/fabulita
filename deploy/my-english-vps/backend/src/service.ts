import type { JsonObject } from "./contracts";
import {
  validateScope,
  validateScoreAnswerInput,
  validateSyncBatch,
} from "./contracts";
import { ApiError } from "./errors";
import { ownerKeyFromUid } from "./hash";
import type { AnswerScorer } from "./llm";
import { findScoringRubric } from "./rubrics";
import type { LearningStore } from "./store";

const CLIENT_IDENTITY_FIELDS = [
  "userId",
  "uid",
  "owner",
  "ownerId",
  "ownerKey",
  "openId",
  "customUserId",
] as const;

export interface BackendServiceDependencies {
  store: LearningStore;
  scorer: AnswerScorer;
  getTrustedUid(): Promise<string | null> | string | null;
  now?: () => number;
  scoreLimitPerMinute?: number;
}

function requestObject(value: unknown): Record<string, unknown> {
  if (value == null || typeof value !== "object" || Array.isArray(value)) {
    throw new ApiError("INVALID_INPUT", "request must be an object.");
  }
  const request = value as Record<string, unknown>;
  for (const field of CLIENT_IDENTITY_FIELDS) {
    if (Object.prototype.hasOwnProperty.call(request, field)) {
      throw new ApiError(
        "CLIENT_IDENTITY_NOT_ALLOWED",
        `${field} is not accepted; identity comes from the server session.`,
      );
    }
  }
  return request;
}

function optionalCursor(value: unknown): string {
  if (value == null || value === "") return "";
  if (typeof value !== "string" || value.length > 100) {
    throw new ApiError("INVALID_CURSOR", "cursor is invalid.");
  }
  return value;
}

async function authenticatedOwnerKey(
  getTrustedUid: BackendServiceDependencies["getTrustedUid"],
): Promise<string> {
  const uid = await getTrustedUid();
  if (typeof uid !== "string" || !uid.trim()) {
    throw new ApiError(
      "AUTHENTICATION_REQUIRED",
      "Sign in before using synced learning data.",
      401,
    );
  }
  return ownerKeyFromUid(uid.trim());
}

export function createBackendService(
  dependencies: BackendServiceDependencies,
) {
  const now = dependencies.now || Date.now;
  const scoreLimit = Math.max(
    1,
    Math.min(60, dependencies.scoreLimitPerMinute || 10),
  );

  return {
    async handle(value: unknown): Promise<JsonObject> {
      const request = requestObject(value);
      const action = request.action;
      if (action === "health") {
        return {
          ok: true,
          service: "my-english-api",
          version: "0.2.0",
          serverTime: new Date(now()).toISOString(),
        };
      }

      if (
        action !== "syncBatch" &&
        action !== "bootstrap" &&
        action !== "scoreAnswer"
      ) {
        throw new ApiError(
          "UNKNOWN_ACTION",
          "action must be health, syncBatch, bootstrap, or scoreAnswer.",
          404,
        );
      }

      const ownerKey = await authenticatedOwnerKey(
        dependencies.getTrustedUid,
      );

      if (action === "syncBatch") {
        const batchInput =
          request.batch != null &&
          typeof request.batch === "object" &&
          !Array.isArray(request.batch)
            ? request.batch
            : request;
        const batch = validateSyncBatch(batchInput, now());
        const result = await dependencies.store.syncBatch(
          ownerKey,
          batch,
          now(),
        );
        return {
          ok: true,
          acknowledgedEventIds: result.acknowledgedEventIds,
          cursor: result.cursor,
          checkpointUpdatedAt: result.checkpointUpdatedAt,
          checkpointVersion: result.checkpointVersion,
        };
      }

      if (action === "bootstrap") {
        const scope = validateScope(request.scope);
        const cursor = optionalCursor(request.cursor);
        const result = await dependencies.store.bootstrap(
          ownerKey,
          scope,
          cursor,
        );
        return {
          ok: true,
          scope: result.scope,
          cursor: result.cursor,
          checkpoint: result.checkpoint as unknown as JsonObject,
          events: result.events,
          hasMore: result.hasMore,
          checkpointVersion: result.checkpoint.version,
        };
      }

      const scoreInput =
        request.payload != null &&
        typeof request.payload === "object" &&
        !Array.isArray(request.payload)
          ? request.payload
          : request;
      const input = validateScoreAnswerInput(scoreInput);
      const rubric = findScoringRubric(
        input.assignmentId,
        input.sectionId,
        input.itemId,
      );
      const rateLimit = await dependencies.store.consumeScoreLimit(
        ownerKey,
        now(),
        scoreLimit,
      );
      if (!rateLimit.allowed) {
        throw new ApiError(
          "RATE_LIMITED",
          "Too many scoring requests. Please try again shortly.",
          429,
          rateLimit.retryAfterMs,
        );
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
