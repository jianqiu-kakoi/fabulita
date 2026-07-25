import { randomBytes, randomUUID } from "node:crypto";
import type { SqliteDatabase } from "./database";
import { sha256 } from "./hash";

const INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
const INVITE_PAYLOAD_LENGTH = 26;
const INVITE_PREFIX = "ME";
const DAY_MS = 24 * 60 * 60 * 1000;

export const INVITE_SECRET_VERSION = 1;
export const DEFAULT_INVITE_TTL_DAYS = 30;

export interface CreateInvitesOptions {
  count?: number;
  emailNormalized?: string | null;
  ttlDays?: number;
  now?: number;
  batchId?: string;
}

export interface CreatedInvite {
  id: string;
  batchId: string;
  code: string;
  emailNormalized: string | null;
  expiresAt: number;
}

function rollback(database: SqliteDatabase): void {
  try {
    database.exec("ROLLBACK");
  } catch {
    // Preserve the original error.
  }
}

function encodeBase32(bytes: Uint8Array): string {
  let buffer = 0;
  let bitCount = 0;
  let output = "";
  for (const byte of bytes) {
    buffer = (buffer << 8) | byte;
    bitCount += 8;
    while (bitCount >= 5) {
      bitCount -= 5;
      output += INVITE_ALPHABET[(buffer >>> bitCount) & 31];
      buffer &= bitCount === 0 ? 0 : (1 << bitCount) - 1;
    }
  }
  if (bitCount > 0) {
    output += INVITE_ALPHABET[(buffer << (5 - bitCount)) & 31];
  }
  return output;
}

export function generateInviteCode(): string {
  // Sixteen CSPRNG bytes provide 128 bits of entropy. Base32 needs 26
  // characters for those 128 bits; the final character carries three bits.
  const payload = encodeBase32(randomBytes(16));
  if (payload.length !== INVITE_PAYLOAD_LENGTH) {
    throw new Error("Invite-code encoder produced an invalid length.");
  }
  return [
    INVITE_PREFIX,
    payload.slice(0, 5),
    payload.slice(5, 10),
    payload.slice(10, 15),
    payload.slice(15, 20),
    payload.slice(20),
  ].join("-");
}

export function normalizeInviteCode(value: unknown): string | null {
  if (typeof value !== "string" || value.length > 80) return null;
  const compact = value
    .trim()
    .toUpperCase()
    .replace(/[-\s]/gu, "");
  if (
    !new RegExp(
      `^${INVITE_PREFIX}[${INVITE_ALPHABET}]{${INVITE_PAYLOAD_LENGTH}}$`,
    ).test(compact)
  ) {
    return null;
  }
  return compact;
}

export function inviteCodeHash(normalizedCode: string): string {
  return sha256(normalizedCode);
}

function positiveInteger(
  value: number | undefined,
  fallback: number,
  maximum: number,
): number {
  if (value == null) return fallback;
  if (!Number.isInteger(value) || value < 1 || value > maximum) {
    throw new Error(`Expected an integer from 1 to ${maximum}.`);
  }
  return value;
}

export function createRegistrationInvites(
  database: SqliteDatabase,
  options: CreateInvitesOptions = {},
): CreatedInvite[] {
  const count = positiveInteger(options.count, 1, 100);
  const ttlDays = positiveInteger(
    options.ttlDays,
    DEFAULT_INVITE_TTL_DAYS,
    365,
  );
  const now = options.now ?? Date.now();
  if (!Number.isSafeInteger(now) || now < 0) {
    throw new Error("Invite creation time must be a non-negative integer.");
  }
  const emailNormalized = options.emailNormalized || null;
  const batchId =
    options.batchId ||
    `invb_${randomBytes(12).toString("base64url")}`;
  if (!/^invb_[A-Za-z0-9_-]{16,80}$/.test(batchId)) {
    throw new Error("Invite batch ID is invalid.");
  }
  const expiresAt = now + ttlDays * DAY_MS;
  const insert = database.prepare(`
    INSERT INTO registration_invites (
      id, code_hash, email_normalized, batch_id, secret_version,
      created_at, expires_at, revoked_at, consumed_at,
      consumed_by_user_id
    ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)
  `);
  const created: CreatedInvite[] = [];

  database.exec("BEGIN IMMEDIATE");
  try {
    for (let index = 0; index < count; index += 1) {
      let inserted = false;
      for (let attempt = 0; attempt < 8 && !inserted; attempt += 1) {
        const code = generateInviteCode();
        const normalized = normalizeInviteCode(code);
        if (!normalized) {
          throw new Error("Generated invite code failed normalization.");
        }
        const id = `inv_${randomUUID().replaceAll("-", "")}`;
        try {
          insert.run(
            id,
            inviteCodeHash(normalized),
            emailNormalized,
            batchId,
            INVITE_SECRET_VERSION,
            now,
            expiresAt,
          );
          created.push({
            id,
            batchId,
            code,
            emailNormalized,
            expiresAt,
          });
          inserted = true;
        } catch (error) {
          const message =
            error instanceof Error ? error.message : String(error);
          if (!message.includes("registration_invites.code_hash")) {
            throw error;
          }
        }
      }
      if (!inserted) {
        throw new Error("Could not generate a unique invite code.");
      }
    }
    database.exec("COMMIT");
    return created;
  } catch (error) {
    rollback(database);
    throw error;
  }
}

export function revokeInviteBatch(
  database: SqliteDatabase,
  batchId: string,
  now = Date.now(),
): number {
  if (!/^invb_[A-Za-z0-9_-]{16,80}$/.test(batchId)) {
    throw new Error("Invite batch ID is invalid.");
  }
  const result = database
    .prepare(`
      UPDATE registration_invites
      SET revoked_at = ?
      WHERE batch_id = ?
        AND revoked_at IS NULL
        AND consumed_at IS NULL
    `)
    .run(now, batchId);
  return Number(result.changes);
}
