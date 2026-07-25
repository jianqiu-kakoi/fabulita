import { dirname } from "node:path";
import { chmodSync, mkdirSync } from "node:fs";
import { DatabaseSync } from "node:sqlite";

export function openDatabase(path: string): DatabaseSync {
  if (!path || path === ":memory:") {
    if (!path) throw new Error("DATABASE_PATH is required.");
  } else {
    mkdirSync(dirname(path), { recursive: true, mode: 0o750 });
  }

  const database = new DatabaseSync(path || ":memory:");
  if (path && path !== ":memory:") chmodSync(path, 0o600);
  database.exec(`
    PRAGMA foreign_keys = ON;
    PRAGMA journal_mode = WAL;
    PRAGMA synchronous = NORMAL;
    PRAGMA busy_timeout = 5000;

    CREATE TABLE IF NOT EXISTS users (
      id TEXT PRIMARY KEY,
      email TEXT NOT NULL,
      email_normalized TEXT NOT NULL UNIQUE,
      password_salt TEXT NOT NULL,
      password_hash TEXT NOT NULL,
      password_hash_version TEXT,
      privacy_consent_version TEXT,
      privacy_consent_accepted_at INTEGER,
      email_verified_at INTEGER,
      created_at INTEGER NOT NULL,
      updated_at INTEGER NOT NULL
    ) STRICT;

    CREATE TABLE IF NOT EXISTS registration_email_verifications (
      challenge_id TEXT PRIMARY KEY,
      email_normalized TEXT NOT NULL,
      code_hash TEXT NOT NULL,
      created_at INTEGER NOT NULL,
      expires_at INTEGER NOT NULL,
      retain_until INTEGER NOT NULL,
      last_sent_at INTEGER NOT NULL,
      attempt_count INTEGER NOT NULL,
      active INTEGER NOT NULL CHECK(active IN (0, 1))
    ) STRICT;

    CREATE TABLE IF NOT EXISTS sessions (
      token_hash TEXT PRIMARY KEY,
      user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      csrf_token TEXT NOT NULL,
      created_at INTEGER NOT NULL,
      expires_at INTEGER NOT NULL,
      last_seen_at INTEGER NOT NULL
    ) STRICT;
    CREATE INDEX IF NOT EXISTS sessions_user_id_idx
      ON sessions(user_id);
    CREATE INDEX IF NOT EXISTS sessions_expires_at_idx
      ON sessions(expires_at);

    CREATE TABLE IF NOT EXISTS auth_rate_limits (
      bucket TEXT NOT NULL,
      subject_hash TEXT NOT NULL,
      window_started_at INTEGER NOT NULL,
      request_count INTEGER NOT NULL,
      expires_at INTEGER NOT NULL,
      PRIMARY KEY (bucket, subject_hash)
    ) STRICT;
    CREATE INDEX IF NOT EXISTS auth_rate_limits_expires_at_idx
      ON auth_rate_limits(expires_at);

    CREATE TABLE IF NOT EXISTS learning_events (
      owner_key TEXT NOT NULL,
      scope TEXT NOT NULL,
      event_id TEXT NOT NULL,
      event_hash TEXT NOT NULL,
      sequence INTEGER NOT NULL,
      received_at INTEGER NOT NULL,
      payload_json TEXT NOT NULL,
      PRIMARY KEY (owner_key, event_id),
      UNIQUE (owner_key, scope, sequence)
    ) STRICT;
    CREATE INDEX IF NOT EXISTS learning_events_bootstrap_idx
      ON learning_events(owner_key, scope, sequence);

    CREATE TABLE IF NOT EXISTS learning_checkpoints (
      owner_key TEXT NOT NULL,
      scope TEXT NOT NULL,
      version INTEGER NOT NULL,
      last_event_sequence INTEGER NOT NULL,
      current_state_json TEXT NOT NULL,
      state_hash TEXT NOT NULL,
      updated_at INTEGER NOT NULL,
      tombstones_json TEXT NOT NULL,
      PRIMARY KEY (owner_key, scope)
    ) STRICT;

    CREATE TABLE IF NOT EXISTS learning_usage (
      owner_key TEXT PRIMARY KEY,
      event_count INTEGER NOT NULL,
      event_bytes INTEGER NOT NULL,
      scope_count INTEGER NOT NULL,
      checkpoint_bytes INTEGER NOT NULL,
      updated_at INTEGER NOT NULL
    ) STRICT;

    CREATE TABLE IF NOT EXISTS learning_rate_limits (
      owner_key TEXT PRIMARY KEY,
      window_started_at INTEGER NOT NULL,
      request_count INTEGER NOT NULL,
      expires_at INTEGER NOT NULL
    ) STRICT;
    CREATE INDEX IF NOT EXISTS learning_rate_limits_expires_at_idx
      ON learning_rate_limits(expires_at);
  `);

  // Existing V0 databases predate consent audit fields, verified-email time,
  // and versioned password hashes. SQLite cannot add several columns in one
  // ALTER TABLE statement, so discover and add only missing nullable columns
  // inside one transaction. Verification challenges are ephemeral; an older
  // single-row schema is safely discarded rather than carrying active codes
  // across this security migration.
  const additions = [
    ["password_hash_version", "TEXT"],
    ["privacy_consent_version", "TEXT"],
    ["privacy_consent_accepted_at", "INTEGER"],
    ["email_verified_at", "INTEGER"],
  ] as const;
  database.exec("BEGIN IMMEDIATE");
  try {
    const userColumns = new Set(
      (
        database
          .prepare("PRAGMA table_info(users)")
          .all() as unknown as Array<{ name: string }>
      ).map((column) => column.name),
    );
    for (const [name, type] of additions) {
      if (!userColumns.has(name)) {
        database.exec(`ALTER TABLE users ADD COLUMN ${name} ${type}`);
      }
    }
    const verificationColumns = database
      .prepare("PRAGMA table_info(registration_email_verifications)")
      .all() as unknown as Array<{ name: string; pk: number }>;
    const challengeIdColumn = verificationColumns.find(
      (column) => column.name === "challenge_id",
    );
    const hasActive = verificationColumns.some(
      (column) => column.name === "active",
    );
    const hasRetainUntil = verificationColumns.some(
      (column) => column.name === "retain_until",
    );
    if (!hasActive || !hasRetainUntil || challengeIdColumn?.pk !== 1) {
      database.exec(`
        DROP TABLE registration_email_verifications;
        CREATE TABLE registration_email_verifications (
          challenge_id TEXT PRIMARY KEY,
          email_normalized TEXT NOT NULL,
          code_hash TEXT NOT NULL,
          created_at INTEGER NOT NULL,
          expires_at INTEGER NOT NULL,
          retain_until INTEGER NOT NULL,
          last_sent_at INTEGER NOT NULL,
          attempt_count INTEGER NOT NULL,
          active INTEGER NOT NULL CHECK(active IN (0, 1))
        ) STRICT;
      `);
    }
    database.exec(`
      CREATE UNIQUE INDEX IF NOT EXISTS
        registration_email_verifications_one_active_idx
        ON registration_email_verifications(email_normalized)
        WHERE active = 1;
      CREATE INDEX IF NOT EXISTS
        registration_email_verifications_email_idx
        ON registration_email_verifications(email_normalized, active, created_at);
      CREATE INDEX IF NOT EXISTS
        registration_email_verifications_retain_until_idx
        ON registration_email_verifications(retain_until);
    `);
    database.exec("COMMIT");
  } catch (error) {
    try {
      database.exec("ROLLBACK");
    } catch {
      // Preserve the migration failure.
    }
    database.close();
    throw error;
  }
  return database;
}

export type SqliteDatabase = DatabaseSync;
