import type {
  JsonObject,
  LearningEvent,
  SyncBatch,
} from "./contracts";
import { ApiError } from "./errors";
import { sha256, stableStringify } from "./hash";
import {
  EMPTY_TOMBSTONES,
  mergeCurrentState,
  type SyncTombstones,
  updateTombstones,
} from "./merge";
import type { SqliteDatabase } from "./database";

interface EventRow {
  owner_key: string;
  scope: string;
  event_id: string;
  event_hash: string;
  sequence: number;
  payload_json: string;
}

interface CheckpointRow {
  owner_key: string;
  scope: string;
  version: number;
  last_event_sequence: number;
  current_state_json: string;
  state_hash: string;
  updated_at: number;
  tombstones_json: string;
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

interface UsageRow {
  event_count: number;
  event_bytes: number;
  scope_count: number;
  checkpoint_bytes: number;
}

export interface LearningStorageQuotas {
  maxEventsPerUser: number;
  maxEventBytesPerUser: number;
  maxScopesPerUser: number;
  maxCheckpointBytesPerUser: number;
}

export const DEFAULT_LEARNING_STORAGE_QUOTAS: LearningStorageQuotas = {
  maxEventsPerUser: 20_000,
  maxEventBytesPerUser: 64 * 1024 * 1024,
  maxScopesPerUser: 20,
  maxCheckpointBytesPerUser: 8 * 1024 * 1024,
};

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

function parseObject<T extends object>(
  value: string,
  fallback: T,
): T {
  try {
    const parsed = JSON.parse(value) as unknown;
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as T;
    }
  } catch {
    // A corrupt database row is an internal error, never client input.
  }
  return fallback;
}

function checkpointFromRow(
  row: CheckpointRow | undefined,
  ownerKey: string,
  scope: string,
): CheckpointRecord {
  if (!row) {
    return {
      ownerKey,
      scope,
      version: 0,
      lastEventSequence: 0,
      currentState: {},
      stateHash: sha256(stableStringify({})),
      updatedAt: 0,
      tombstones: {
        assignmentResetAt: {},
        questionDeletedAt: {},
      },
    };
  }
  const currentState = parseObject<JsonObject>(
    row.current_state_json,
    {},
  );
  return {
    ownerKey,
    scope,
    version: Number(row.version) || 0,
    lastEventSequence: Number(row.last_event_sequence) || 0,
    currentState,
    stateHash:
      typeof row.state_hash === "string" && row.state_hash
        ? row.state_hash
        : sha256(stableStringify(currentState)),
    updatedAt: Number(row.updated_at) || 0,
    tombstones: parseObject<SyncTombstones>(
      row.tombstones_json,
      EMPTY_TOMBSTONES,
    ),
  };
}

function rollback(database: SqliteDatabase): void {
  try {
    database.exec("ROLLBACK");
  } catch {
    // Preserve the original transaction error.
  }
}

export class SqliteLearningStore implements LearningStore {
  private readonly quotas: LearningStorageQuotas;

  constructor(
    private readonly database: SqliteDatabase,
    quotas: Partial<LearningStorageQuotas> = {},
  ) {
    this.quotas = {
      ...DEFAULT_LEARNING_STORAGE_QUOTAS,
      ...quotas,
    };
  }

  private usage(ownerKey: string): {
    value: UsageRow;
    existed: boolean;
  } {
    const row = this.database
      .prepare(`
        SELECT event_count, event_bytes, scope_count, checkpoint_bytes
        FROM learning_usage
        WHERE owner_key = ?
      `)
      .get(ownerKey) as UsageRow | undefined;
    if (row) {
      return {
        existed: true,
        value: {
          event_count: Number(row.event_count) || 0,
          event_bytes: Number(row.event_bytes) || 0,
          scope_count: Number(row.scope_count) || 0,
          checkpoint_bytes: Number(row.checkpoint_bytes) || 0,
        },
      };
    }

    const eventUsage = this.database
      .prepare(`
        SELECT COUNT(*) AS event_count,
               COALESCE(SUM(length(CAST(payload_json AS BLOB))), 0)
                 AS event_bytes
        FROM learning_events
        WHERE owner_key = ?
      `)
      .get(ownerKey) as {
        event_count: number;
        event_bytes: number;
      };
    const checkpointUsage = this.database
      .prepare(`
        SELECT COUNT(*) AS scope_count,
               COALESCE(SUM(
                 length(CAST(current_state_json AS BLOB)) +
                 length(CAST(tombstones_json AS BLOB))
               ), 0) AS checkpoint_bytes
        FROM learning_checkpoints
        WHERE owner_key = ?
      `)
      .get(ownerKey) as {
        scope_count: number;
        checkpoint_bytes: number;
      };
    return {
      existed: false,
      value: {
        event_count: Number(eventUsage.event_count) || 0,
        event_bytes: Number(eventUsage.event_bytes) || 0,
        scope_count: Number(checkpointUsage.scope_count) || 0,
        checkpoint_bytes:
          Number(checkpointUsage.checkpoint_bytes) || 0,
      },
    };
  }

  async syncBatch(
    ownerKey: string,
    batch: SyncBatch,
    now: number,
  ): Promise<SyncStoreResult> {
    this.database.exec("BEGIN IMMEDIATE");
    try {
      const usage = this.usage(ownerKey);
      const row = this.database
        .prepare(`
          SELECT owner_key, scope, version, last_event_sequence,
                 current_state_json, state_hash, updated_at,
                 tombstones_json
          FROM learning_checkpoints
          WHERE owner_key = ? AND scope = ?
        `)
        .get(ownerKey, batch.scope) as CheckpointRow | undefined;
      const current = checkpointFromRow(row, ownerKey, batch.scope);

      if (batch.baseCheckpointVersion > current.version) {
        throw new ApiError(
          "CHECKPOINT_AHEAD",
          "baseCheckpointVersion is newer than the server checkpoint.",
          409,
        );
      }

      const newEvents: Array<{
        event: LearningEvent;
        hash: string;
        payloadJson: string;
        payloadBytes: number;
      }> = [];
      const findEvent = this.database.prepare(`
        SELECT owner_key, scope, event_id, event_hash, sequence,
               payload_json
        FROM learning_events
        WHERE owner_key = ? AND event_id = ?
      `);
      for (const event of batch.events) {
        const eventHash = sha256(stableStringify(event));
        const existing = findEvent.get(
          ownerKey,
          event.id,
        ) as EventRow | undefined;
        if (existing) {
          if (
            existing.owner_key !== ownerKey ||
            existing.event_id !== event.id ||
            existing.event_hash !== eventHash
          ) {
            throw new ApiError(
              "EVENT_ID_CONFLICT",
              `Event ${event.id} is immutable and already has different content.`,
              409,
            );
          }
        } else {
          const payloadJson = JSON.stringify(event);
          newEvents.push({
            event,
            hash: eventHash,
            payloadJson,
            payloadBytes: Buffer.byteLength(payloadJson),
          });
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
      const currentStateJson = JSON.stringify(mergedState);
      const tombstonesJson = JSON.stringify(tombstones);
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
      const oldCheckpointBytes = row
        ? Buffer.byteLength(row.current_state_json) +
          Buffer.byteLength(row.tombstones_json)
        : 0;
      const newCheckpointBytes =
        Buffer.byteLength(currentStateJson) +
        Buffer.byteLength(tombstonesJson);
      const proposedUsage: UsageRow = {
        event_count:
          usage.value.event_count + newEvents.length,
        event_bytes:
          usage.value.event_bytes +
          newEvents.reduce(
            (total, entry) => total + entry.payloadBytes,
            0,
          ),
        scope_count:
          usage.value.scope_count + (row ? 0 : 1),
        checkpoint_bytes:
          usage.value.checkpoint_bytes -
          oldCheckpointBytes +
          newCheckpointBytes,
      };
      if (
        proposedUsage.event_count > this.quotas.maxEventsPerUser ||
        proposedUsage.event_bytes >
          this.quotas.maxEventBytesPerUser ||
        proposedUsage.scope_count > this.quotas.maxScopesPerUser ||
        proposedUsage.checkpoint_bytes >
          this.quotas.maxCheckpointBytesPerUser
      ) {
        throw new ApiError(
          "STORAGE_QUOTA_EXCEEDED",
          "The learning-data storage quota for this account has been reached.",
          413,
        );
      }

      const insertEvent = this.database.prepare(`
        INSERT INTO learning_events (
          owner_key, scope, event_id, event_hash, sequence,
          received_at, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
      `);
      for (const entry of newEvents) {
        nextSequence += 1;
        insertEvent.run(
          ownerKey,
          batch.scope,
          entry.event.id,
          entry.hash,
          nextSequence,
          now,
          entry.payloadJson,
        );
      }

      const checkpointUpdatedAt = checkpointChanged
        ? now
        : current.updatedAt;
      if (checkpointChanged) {
        this.database
          .prepare(`
            INSERT INTO learning_checkpoints (
              owner_key, scope, version, last_event_sequence,
              current_state_json, state_hash, updated_at,
              tombstones_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(owner_key, scope) DO UPDATE SET
              version = excluded.version,
              last_event_sequence = excluded.last_event_sequence,
              current_state_json = excluded.current_state_json,
              state_hash = excluded.state_hash,
              updated_at = excluded.updated_at,
              tombstones_json = excluded.tombstones_json
          `)
          .run(
            ownerKey,
            batch.scope,
            version,
            nextSequence,
            currentStateJson,
            stateHash,
            checkpointUpdatedAt,
            tombstonesJson,
          );
      }
      if (
        !usage.existed ||
        newEvents.length > 0 ||
        checkpointChanged
      ) {
        this.database
          .prepare(`
            INSERT INTO learning_usage (
              owner_key, event_count, event_bytes, scope_count,
              checkpoint_bytes, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(owner_key) DO UPDATE SET
              event_count = excluded.event_count,
              event_bytes = excluded.event_bytes,
              scope_count = excluded.scope_count,
              checkpoint_bytes = excluded.checkpoint_bytes,
              updated_at = excluded.updated_at
          `)
          .run(
            ownerKey,
            proposedUsage.event_count,
            proposedUsage.event_bytes,
            proposedUsage.scope_count,
            proposedUsage.checkpoint_bytes,
            now,
          );
      }

      this.database.exec("COMMIT");
      return {
        acknowledgedEventIds: batch.events.map((event) => event.id),
        cursor: cursorFor(version, nextSequence),
        checkpointUpdatedAt,
        checkpointVersion: version,
      };
    } catch (error) {
      rollback(this.database);
      throw error;
    }
  }

  async bootstrap(
    ownerKey: string,
    scope: string,
    cursor: string,
    requestedLimit = 200,
  ): Promise<BootstrapStoreResult> {
    const parsedCursor = parseCursor(cursor);
    const row = this.database
      .prepare(`
        SELECT owner_key, scope, version, last_event_sequence,
               current_state_json, state_hash, updated_at,
               tombstones_json
        FROM learning_checkpoints
        WHERE owner_key = ? AND scope = ?
      `)
      .get(ownerKey, scope) as CheckpointRow | undefined;
    const checkpoint = checkpointFromRow(row, ownerKey, scope);
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
    const rows = this.database
      .prepare(`
        SELECT owner_key, scope, event_id, event_hash, sequence,
               payload_json
        FROM learning_events
        WHERE owner_key = ? AND scope = ? AND sequence > ?
        ORDER BY sequence ASC
        LIMIT ?
      `)
      .all(
        ownerKey,
        scope,
        parsedCursor.eventSequence,
        limit + 1,
      ) as unknown as EventRow[];
    const hasMore = rows.length > limit;
    const page = rows.slice(0, limit);
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
      events: page.map((event) =>
        JSON.parse(event.payload_json) as LearningEvent
      ),
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
    this.database.exec("BEGIN IMMEDIATE");
    try {
      const previous = this.database
        .prepare(`
          SELECT window_started_at, request_count
          FROM learning_rate_limits
          WHERE owner_key = ?
        `)
        .get(ownerKey) as
          | { window_started_at: number; request_count: number }
          | undefined;
      const previousCount =
        previous?.window_started_at === windowStartedAt
          ? Number(previous.request_count) || 0
          : 0;
      if (previousCount >= limit) {
        this.database.exec("COMMIT");
        return { allowed: false, retryAfterMs };
      }
      this.database
        .prepare(`
          INSERT INTO learning_rate_limits (
            owner_key, window_started_at, request_count, expires_at
          ) VALUES (?, ?, ?, ?)
          ON CONFLICT(owner_key) DO UPDATE SET
            window_started_at = excluded.window_started_at,
            request_count = excluded.request_count,
            expires_at = excluded.expires_at
        `)
        .run(
          ownerKey,
          windowStartedAt,
          previousCount + 1,
          windowStartedAt + 2 * 60_000,
        );
      this.database.exec("COMMIT");
      return { allowed: true, retryAfterMs };
    } catch (error) {
      rollback(this.database);
      throw error;
    }
  }
}
