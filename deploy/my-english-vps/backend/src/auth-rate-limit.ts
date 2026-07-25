import type { SqliteDatabase } from "./database";
import { sha256 } from "./hash";

export interface AuthRateLimitRule {
  bucket: string;
  subject: string;
  limit: number;
  windowMs: number;
}

export interface AuthRateLimitResult {
  allowed: boolean;
  retryAfterMs: number;
}

interface RateLimitRow {
  window_started_at: number;
  request_count: number;
}

function rollback(database: SqliteDatabase): void {
  try {
    database.exec("ROLLBACK");
  } catch {
    // Preserve the original error.
  }
}

export class SqliteAuthRateLimiter {
  constructor(private readonly database: SqliteDatabase) {}

  consume(
    rules: AuthRateLimitRule[],
    now: number,
  ): AuthRateLimitResult {
    const normalized = rules.map((rule) => ({
      bucket: rule.bucket.slice(0, 80),
      subjectHash: sha256(`${rule.bucket}\u0000${rule.subject}`),
      limit: Math.max(1, Math.min(10_000, Math.floor(rule.limit))),
      windowMs: Math.max(
        60_000,
        Math.min(24 * 60 * 60_000, Math.floor(rule.windowMs)),
      ),
    }));

    this.database.exec("BEGIN IMMEDIATE");
    try {
      this.database
        .prepare("DELETE FROM auth_rate_limits WHERE expires_at <= ?")
        .run(now);
      const read = this.database.prepare(`
        SELECT window_started_at, request_count
        FROM auth_rate_limits
        WHERE bucket = ? AND subject_hash = ?
      `);
      const states = normalized.map((rule) => {
        const windowStartedAt =
          Math.floor(now / rule.windowMs) * rule.windowMs;
        const row = read.get(
          rule.bucket,
          rule.subjectHash,
        ) as RateLimitRow | undefined;
        const count =
          row?.window_started_at === windowStartedAt
            ? Number(row.request_count) || 0
            : 0;
        return {
          ...rule,
          windowStartedAt,
          count,
          retryAfterMs: windowStartedAt + rule.windowMs - now,
        };
      });
      const blocked = states.filter((state) => state.count >= state.limit);
      if (blocked.length > 0) {
        this.database.exec("COMMIT");
        return {
          allowed: false,
          retryAfterMs: Math.max(
            ...blocked.map((state) => state.retryAfterMs),
          ),
        };
      }

      const upsert = this.database.prepare(`
        INSERT INTO auth_rate_limits (
          bucket, subject_hash, window_started_at,
          request_count, expires_at
        ) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(bucket, subject_hash) DO UPDATE SET
          window_started_at = excluded.window_started_at,
          request_count = excluded.request_count,
          expires_at = excluded.expires_at
      `);
      for (const state of states) {
        upsert.run(
          state.bucket,
          state.subjectHash,
          state.windowStartedAt,
          state.count + 1,
          state.windowStartedAt + 2 * state.windowMs,
        );
      }
      this.database.exec("COMMIT");
      return { allowed: true, retryAfterMs: 0 };
    } catch (error) {
      rollback(this.database);
      throw error;
    }
  }
}
