import type {
  JsonObject,
  LearningEvent,
  SyncBatch,
} from "./contracts";
import { ApiError } from "./errors";
import {
  checkpointDocumentId,
  eventDocumentId,
  rateLimitDocumentId,
  sha256,
  stableStringify,
} from "./hash";
import {
  EMPTY_TOMBSTONES,
  mergeCurrentState,
  type SyncTombstones,
  updateTombstones,
} from "./merge";

const EVENTS_COLLECTION = "learning_events";
const CHECKPOINTS_COLLECTION = "learning_checkpoints";
const RATE_LIMITS_COLLECTION = "learning_rate_limits";

interface DocumentResult {
  data?: unknown;
}

interface DocumentReference {
  get(): Promise<DocumentResult>;
  set(value: Record<string, unknown>): Promise<unknown>;
}

interface QueryReference {
  where(value: Record<string, unknown>): QueryReference;
  orderBy(field: string, direction: "asc" | "desc"): QueryReference;
  limit(limit: number): QueryReference;
  get(): Promise<DocumentResult>;
}

interface CollectionReference extends QueryReference {
  doc(id: string): DocumentReference;
}

interface TransactionReference {
  collection(name: string): CollectionReference;
}

export interface CloudBaseDatabase {
  collection(name: string): CollectionReference;
  command: {
    gt(value: number): unknown;
  };
  runTransaction<T>(
    update: (transaction: TransactionReference) => Promise<T>,
  ): Promise<T | { result: T; errMsg?: string }>;
}

interface EventRecord {
  ownerKey: string;
  scope: string;
  eventId: string;
  eventHash: string;
  sequence: number;
  receivedAt: number;
  payload: LearningEvent;
}

interface CheckpointRecord {
  ownerKey: string;
  scope: string;
  version: number;
  lastEventSequence: number;
  currentState: JsonObject;
  stateHash: string;
  updatedAt: number;
  tombstones: SyncTombstones;
}

export interface SyncStoreResult {
  acknowledgedEventIds: string[];
  cursor: string;
  checkpointUpdatedAt: number;
  checkpointVersion: number;
}

export interface BootstrapStoreResult {
  scope: string;
  cursor: string;
  checkpoint: {
    currentState: JsonObject;
    updatedAt: number;
    version: number;
  };
  events: LearningEvent[];
  hasMore: boolean;
}

export interface RateLimitResult {
  allowed: boolean;
  retryAfterMs: number;
}

export interface LearningStore {
  syncBatch(
    ownerKey: string,
    batch: SyncBatch,
    now: number,
  ): Promise<SyncStoreResult>;
  bootstrap(
    ownerKey: string,
    scope: string,
    cursor: string,
    limit?: number,
  ): Promise<BootstrapStoreResult>;
  consumeScoreLimit(
    ownerKey: string,
    now: number,
    limit: number,
  ): Promise<RateLimitResult>;
}

function firstDocument<T>(result: DocumentResult): T | undefined {
  const data = result && result.data;
  if (Array.isArray(data)) return data[0] as T | undefined;
  if (data && typeof data === "object") return data as T;
  return undefined;
}

async function unwrapTransaction<T>(
  promise: Promise<T | { result: T; errMsg?: string }>,
): Promise<T> {
  const value = await promise;
  if (
    value != null &&
    typeof value === "object" &&
    "result" in value
  ) {
    return (value as { result: T }).result;
  }
  return value as T;
}

function cursorFor(version: number, eventSequence: number): string {
  return `c:${version}:${eventSequence}`;
}

export function parseCursor(cursor: string): {
  checkpointVersion: number;
  eventSequence: number;
} {
  if (!cursor) return { checkpointVersion: 0, eventSequence: 0 };
  const match = /^c:(\d+):(\d+)$/.exec(cursor);
  if (!match) {
    throw new ApiError("INVALID_CURSOR", "cursor has an invalid format.");
  }
  const checkpointVersion = Number(match[1]);
  const eventSequence = Number(match[2]);
  if (
    !Number.isSafeInteger(checkpointVersion) ||
    !Number.isSafeInteger(eventSequence)
  ) {
    throw new ApiError("INVALID_CURSOR", "cursor is outside valid bounds.");
  }
  return { checkpointVersion, eventSequence };
}

function checkpointFromDocument(
  raw: CheckpointRecord | undefined,
  ownerKey: string,
  scope: string,
): CheckpointRecord {
  if (!raw) {
    return {
      ownerKey,
      scope,
      version: 0,
      lastEventSequence: 0,
      currentState: {},
      stateHash: stableStringify({}),
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
    currentState:
      raw.currentState &&
      typeof raw.currentState === "object" &&
      !Array.isArray(raw.currentState)
        ? raw.currentState
        : {},
    stateHash:
      typeof raw.stateHash === "string"
        ? raw.stateHash
        : stableStringify(raw.currentState || {}),
    updatedAt: Number(raw.updatedAt) || 0,
    tombstones: raw.tombstones || EMPTY_TOMBSTONES,
  };
}

export class CloudBaseLearningStore implements LearningStore {
  constructor(private readonly database: CloudBaseDatabase) {}

  async syncBatch(
    ownerKey: string,
    batch: SyncBatch,
    now: number,
  ): Promise<SyncStoreResult> {
    const checkpointId = checkpointDocumentId(ownerKey, batch.scope);

    return unwrapTransaction(
      this.database.runTransaction(async (transaction) => {
        const checkpointReference = transaction
          .collection(CHECKPOINTS_COLLECTION)
          .doc(checkpointId);
        const checkpointResult = await checkpointReference.get();
        const current = checkpointFromDocument(
          firstDocument<CheckpointRecord>(checkpointResult),
          ownerKey,
          batch.scope,
        );

        if (batch.baseCheckpointVersion > current.version) {
          throw new ApiError(
            "CHECKPOINT_AHEAD",
            "baseCheckpointVersion is newer than the server checkpoint.",
            409,
          );
        }

        const newEvents: Array<{
          reference: DocumentReference;
          event: LearningEvent;
          hash: string;
        }> = [];

        for (const event of batch.events) {
          const eventHash = sha256(stableStringify(event));
          const reference = transaction
            .collection(EVENTS_COLLECTION)
            .doc(eventDocumentId(ownerKey, event.id));
          const existing = firstDocument<EventRecord>(
            await reference.get(),
          );
          if (existing) {
            if (
              existing.ownerKey !== ownerKey ||
              existing.eventId !== event.id ||
              existing.eventHash !== eventHash
            ) {
              throw new ApiError(
                "EVENT_ID_CONFLICT",
                `Event ${event.id} is immutable and already has different content.`,
                409,
              );
            }
          } else {
            newEvents.push({ reference, event, hash: eventHash });
          }
        }

        const tombstones = updateTombstones(
          current.tombstones,
          batch.events,
        );
        const mergedState = mergeCurrentState(
          current.currentState,
          batch.currentState,
          tombstones,
        );
        const stateHash = sha256(stableStringify(mergedState));
        const tombstoneHash = sha256(
          stableStringify(tombstones as unknown as JsonObject),
        );
        const previousTombstoneHash = sha256(
          stableStringify(
            current.tombstones as unknown as JsonObject,
          ),
        );
        const checkpointChanged =
          newEvents.length > 0 ||
          stateHash !== current.stateHash ||
          tombstoneHash !== previousTombstoneHash ||
          current.version === 0;
        const version = checkpointChanged
          ? current.version + 1
          : current.version;
        let nextSequence = current.lastEventSequence;

        for (const entry of newEvents) {
          nextSequence += 1;
          const record: EventRecord = {
            ownerKey,
            scope: batch.scope,
            eventId: entry.event.id,
            eventHash: entry.hash,
            sequence: nextSequence,
            receivedAt: now,
            payload: entry.event,
          };
          await entry.reference.set(
            record as unknown as Record<string, unknown>,
          );
        }

        const checkpointUpdatedAt = checkpointChanged
          ? now
          : current.updatedAt;
        if (checkpointChanged) {
          const checkpoint: CheckpointRecord = {
            ownerKey,
            scope: batch.scope,
            version,
            lastEventSequence: nextSequence,
            currentState: mergedState,
            stateHash,
            updatedAt: checkpointUpdatedAt,
            tombstones,
          };
          await checkpointReference.set(
            checkpoint as unknown as Record<string, unknown>,
          );
        }

        return {
          acknowledgedEventIds: batch.events.map((event) => event.id),
          cursor: cursorFor(version, nextSequence),
          checkpointUpdatedAt,
          checkpointVersion: version,
        };
      }),
    );
  }

  async bootstrap(
    ownerKey: string,
    scope: string,
    cursor: string,
    requestedLimit = 200,
  ): Promise<BootstrapStoreResult> {
    const parsedCursor = parseCursor(cursor);
    const checkpointResult = await this.database
      .collection(CHECKPOINTS_COLLECTION)
      .doc(checkpointDocumentId(ownerKey, scope))
      .get();
    const checkpoint = checkpointFromDocument(
      firstDocument<CheckpointRecord>(checkpointResult),
      ownerKey,
      scope,
    );

    if (
      parsedCursor.checkpointVersion > checkpoint.version ||
      parsedCursor.eventSequence > checkpoint.lastEventSequence
    ) {
      throw new ApiError(
        "INVALID_CURSOR",
        "cursor is ahead of the server checkpoint.",
        409,
      );
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
      ? (queryResult.data as EventRecord[])
      : [];
    const hasMore = records.length > limit;
    const page = records.slice(0, limit);
    const eventSequence =
      page.length > 0
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

  async consumeScoreLimit(
    ownerKey: string,
    now: number,
    limit: number,
  ): Promise<RateLimitResult> {
    const windowStartedAt = Math.floor(now / 60_000) * 60_000;
    const retryAfterMs = windowStartedAt + 60_000 - now;
    const documentId = rateLimitDocumentId(ownerKey);

    return unwrapTransaction(
      this.database.runTransaction(async (transaction) => {
        const reference = transaction
          .collection(RATE_LIMITS_COLLECTION)
          .doc(documentId);
        const previous = firstDocument<{
          windowStartedAt?: number;
          count?: number;
        }>(await reference.get());
        const previousCount =
          previous?.windowStartedAt === windowStartedAt
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
      }),
    );
  }
}

export const CLOUD_DATABASE_COLLECTIONS = {
  events: EVENTS_COLLECTION,
  checkpoints: CHECKPOINTS_COLLECTION,
  rateLimits: RATE_LIMITS_COLLECTION,
} as const;
