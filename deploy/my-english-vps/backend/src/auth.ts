import {
  createHmac,
  randomBytes,
  randomInt,
  randomUUID,
  scrypt,
  timingSafeEqual,
} from "node:crypto";
import type { SqliteDatabase } from "./database";
import {
  EMAIL_VERIFICATION_MAX_ATTEMPTS,
  EMAIL_VERIFICATION_RESEND_SECONDS,
  EMAIL_VERIFICATION_TTL_SECONDS,
} from "./email-verification";
import { ApiError } from "./errors";
import { sha256 } from "./hash";

const SCRYPT_KEY_LENGTH = 64;
export const PRIVACY_CONSENT_VERSION = "2026-07-25";
export const CURRENT_PASSWORD_HASH_VERSION =
  "scrypt-v2-n131072-r8-p1";
export const LEGACY_PASSWORD_HASH_VERSION =
  "scrypt-v1-n16384-r8-p1";

interface ScryptProfile {
  version: string;
  N: number;
  r: number;
  p: number;
  maxmem: number;
}

const LEGACY_SCRYPT_PROFILE: ScryptProfile = {
  version: LEGACY_PASSWORD_HASH_VERSION,
  N: 16_384,
  r: 8,
  p: 1,
  maxmem: 64 * 1024 * 1024,
};

const CURRENT_SCRYPT_PROFILE: ScryptProfile = {
  version: CURRENT_PASSWORD_HASH_VERSION,
  N: 131_072,
  r: 8,
  p: 1,
  maxmem: 192 * 1024 * 1024,
};

interface UserRow {
  id: string;
  email: string;
  email_normalized: string;
  password_salt: string;
  password_hash: string;
  password_hash_version: string | null;
  privacy_consent_version: string | null;
  privacy_consent_accepted_at: number | null;
  email_verified_at: number | null;
  created_at: number;
}

interface RegistrationEmailVerificationRow {
  email_normalized: string;
  challenge_id: string;
  code_hash: string;
  created_at: number;
  expires_at: number;
  retain_until: number;
  last_sent_at: number;
  attempt_count: number;
  active: number;
}

interface SessionRow extends UserRow {
  token_hash: string;
  csrf_token: string;
  expires_at: number;
  last_seen_at: number;
}

export interface PublicUser {
  id: string;
  email: string;
  createdAt: number;
}

export interface AuthenticatedSession {
  user: PublicUser;
  csrfToken: string;
  expiresAt: number;
}

export interface NewSession extends AuthenticatedSession {
  sessionToken: string;
}

export interface PasswordWorkOptions {
  concurrency?: number;
  queueLimit?: number;
}

export interface EmailVerificationOptions {
  secret?: string;
}

export interface IssuedRegistrationVerification {
  challengeId: string;
  code: string;
  expiresAt: number;
}

class PasswordWorkLimiter {
  private active = 0;
  private readonly waiters: Array<() => void> = [];
  private readonly concurrency: number;
  private readonly queueLimit: number;

  constructor(options: PasswordWorkOptions) {
    this.concurrency = Math.max(
      1,
      Math.min(2, Math.floor(options.concurrency || 2)),
    );
    this.queueLimit = Math.max(
      0,
      Math.min(64, Math.floor(options.queueLimit ?? 8)),
    );
  }

  private async acquire(): Promise<void> {
    if (this.active < this.concurrency) {
      this.active += 1;
      return;
    }
    if (this.waiters.length >= this.queueLimit) {
      throw new ApiError(
        "AUTH_CAPACITY_REACHED",
        "Authentication is temporarily busy. Please try again shortly.",
        503,
        1000,
      );
    }
    await new Promise<void>((resolve) => this.waiters.push(resolve));
  }

  private release(): void {
    const next = this.waiters.shift();
    if (next) {
      // Transfer the occupied slot directly to the oldest waiter.
      next();
    } else {
      this.active -= 1;
    }
  }

  async run<T>(work: () => Promise<T>): Promise<T> {
    await this.acquire();
    try {
      return await work();
    } finally {
      this.release();
    }
  }
}

function scryptPassword(
  password: string,
  salt: string,
  profile: ScryptProfile,
): Promise<Uint8Array> {
  return new Promise((resolve, reject) => {
    scrypt(
      password,
      salt,
      SCRYPT_KEY_LENGTH,
      {
        N: profile.N,
        r: profile.r,
        p: profile.p,
        maxmem: profile.maxmem,
      },
      (error, derivedKey) => {
        if (error) reject(error);
        else resolve(derivedKey);
      },
    );
  });
}

function inputObject(value: unknown): Record<string, unknown> {
  if (value == null || typeof value !== "object" || Array.isArray(value)) {
    throw new ApiError("INVALID_INPUT", "request must be an object.");
  }
  return value as Record<string, unknown>;
}

export function normalizeEmail(value: unknown): string {
  if (typeof value !== "string") {
    throw new ApiError("INVALID_EMAIL", "Enter a valid email address.");
  }
  const email = value.trim().toLowerCase();
  if (
    email.length < 3 ||
    email.length > 254 ||
    !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
  ) {
    throw new ApiError("INVALID_EMAIL", "Enter a valid email address.");
  }
  return email;
}

function validatePassword(value: unknown): string {
  if (typeof value !== "string") {
    throw new ApiError(
      "INVALID_PASSWORD",
      "Password must be a string.",
    );
  }
  if (value.length < 10) {
    throw new ApiError(
      "WEAK_PASSWORD",
      "Password must contain at least 10 characters.",
    );
  }
  if (value.length > 128) {
    throw new ApiError(
      "INVALID_PASSWORD",
      "Password must contain at most 128 characters.",
    );
  }
  return value;
}

export function assertCurrentPrivacyConsent(
  input: Record<string, unknown>,
): void {
  const raw = input.privacyConsent;
  if (
    raw == null ||
    typeof raw !== "object" ||
    Array.isArray(raw) ||
    (raw as Record<string, unknown>).accepted !== true ||
    (raw as Record<string, unknown>).version !==
      PRIVACY_CONSENT_VERSION
  ) {
    throw new ApiError(
      "PRIVACY_CONSENT_REQUIRED",
      `Registration requires acceptance of privacy notice ${PRIVACY_CONSENT_VERSION}.`,
      400,
    );
  }
}

export function registrationVerificationEmail(value: unknown): string {
  const input = inputObject(value);
  assertCurrentPrivacyConsent(input);
  return normalizeEmail(input.email);
}

function publicUser(row: UserRow): PublicUser {
  return {
    id: row.id,
    email: row.email,
    createdAt: Number(row.created_at),
  };
}

function sessionToken(): string {
  return randomBytes(32).toString("base64url");
}

function csrfToken(): string {
  return randomBytes(32).toString("base64url");
}

function rollback(database: SqliteDatabase): void {
  try {
    database.exec("ROLLBACK");
  } catch {
    // Preserve the original error.
  }
}

export class SqliteAuthStore {
  private readonly sessionTtlMs: number;
  private readonly passwordWork: PasswordWorkLimiter;
  private readonly emailVerificationSecret: string;

  constructor(
    private readonly database: SqliteDatabase,
    sessionTtlDays = 30,
    passwordWorkOptions: PasswordWorkOptions = {},
    emailVerificationOptions: EmailVerificationOptions = {},
  ) {
    this.sessionTtlMs =
      Math.max(1, Math.min(90, sessionTtlDays)) * 24 * 60 * 60 * 1000;
    this.passwordWork = new PasswordWorkLimiter(passwordWorkOptions);
    this.emailVerificationSecret =
      emailVerificationOptions.secret || "";
  }

  private registrationCodeHash(
    email: string,
    challengeId: string,
    code: string,
  ): string {
    return createHmac("sha256", this.emailVerificationSecret)
      .update("registration-email")
      .update("\0")
      .update(email)
      .update("\0")
      .update(challengeId)
      .update("\0")
      .update(code)
      .digest("hex");
  }

  private assertEmailVerificationConfigured(): void {
    if (Buffer.byteLength(this.emailVerificationSecret, "utf8") < 32) {
      throw new ApiError(
        "EMAIL_VERIFICATION_UNAVAILABLE",
        "Email verification is temporarily unavailable.",
        503,
      );
    }
  }

  registrationVerificationRetryAfter(
    email: string,
    now: number,
  ): number {
    const row = this.database
      .prepare(`
        SELECT last_sent_at, expires_at, attempt_count
        FROM registration_email_verifications
        WHERE email_normalized = ? AND active = 1 AND expires_at > ?
      `)
      .get(email, now) as
        | {
            last_sent_at: number;
            expires_at: number;
            attempt_count: number;
          }
        | undefined;
    if (!row) return 0;
    if (
      Number(row.attempt_count) >= EMAIL_VERIFICATION_MAX_ATTEMPTS
    ) {
      return Math.max(0, Number(row.expires_at) - now);
    }
    return Math.max(
      0,
      Number(row.last_sent_at) +
        EMAIL_VERIFICATION_RESEND_SECONDS * 1000 -
        now,
    );
  }

  issueRegistrationVerification(
    email: string,
    now: number,
  ): IssuedRegistrationVerification {
    this.assertEmailVerificationConfigured();
    const challengeId = randomBytes(18).toString("base64url");
    const expiresAt =
      now + EMAIL_VERIFICATION_TTL_SECONDS * 1000;
    let code = "";
    let codeHash = "";

    this.database.exec("BEGIN IMMEDIATE");
    try {
      this.database
        .prepare(`
          DELETE FROM registration_email_verifications
          WHERE retain_until <= ?
        `)
        .run(now);
      this.database
        .prepare(`
          UPDATE registration_email_verifications
          SET active = 0
          WHERE active = 1 AND expires_at <= ?
        `)
        .run(now);
      const existing = this.database
        .prepare(`
          SELECT email_normalized, challenge_id, code_hash, created_at,
                 expires_at, retain_until, last_sent_at, attempt_count,
                 active
          FROM registration_email_verifications
          WHERE email_normalized = ? AND active = 1 AND expires_at > ?
        `)
        .get(email, now) as RegistrationEmailVerificationRow | undefined;
      if (
        existing &&
        Number(existing.attempt_count) >=
          EMAIL_VERIFICATION_MAX_ATTEMPTS
      ) {
        const retryAfterMs =
          Number(existing.expires_at) - now;
        this.database.exec("COMMIT");
        throw new ApiError(
          "VERIFICATION_RATE_LIMITED",
          "Too many verification attempts. Please try again later.",
          429,
          retryAfterMs,
        );
      }
      if (
        existing &&
        now - Number(existing.last_sent_at) <
          EMAIL_VERIFICATION_RESEND_SECONDS * 1000
      ) {
        const retryAfterMs =
          Number(existing.last_sent_at) +
          EMAIL_VERIFICATION_RESEND_SECONDS * 1000 -
          now;
        this.database.exec("COMMIT");
        throw new ApiError(
          "VERIFICATION_RATE_LIMITED",
          "Please wait before requesting another verification code.",
          429,
          retryAfterMs,
        );
      }
      const history = this.database
        .prepare(`
          SELECT email_normalized, challenge_id, code_hash, created_at,
                 expires_at, retain_until, last_sent_at, attempt_count,
                 active
          FROM registration_email_verifications
          WHERE email_normalized = ?
          ORDER BY created_at DESC
        `)
        .all(email) as unknown as RegistrationEmailVerificationRow[];
      do {
        code = randomInt(0, 1_000_000).toString().padStart(6, "0");
      } while (
        history.some((challenge) =>
          this.registrationCodeMatches(challenge, code)
        )
      );
      codeHash = this.registrationCodeHash(
        email,
        challengeId,
        code,
      );
      this.database
        .prepare(`
          UPDATE registration_email_verifications
          SET active = 0,
              retain_until = MAX(retain_until, ?)
          WHERE email_normalized = ?
        `)
        .run(expiresAt, email);
      const carriedAttempts = history.reduce(
        (maximum, challenge) =>
          Math.max(maximum, Number(challenge.attempt_count) || 0),
        0,
      );
      this.database
        .prepare(`
          INSERT INTO registration_email_verifications (
            challenge_id, email_normalized, code_hash, created_at,
            expires_at, retain_until, last_sent_at, attempt_count, active
          ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
        `)
        .run(
          challengeId,
          email,
          codeHash,
          now,
          expiresAt,
          expiresAt,
          now,
          carriedAttempts,
        );
      this.database.exec("COMMIT");
      return { challengeId, code, expiresAt };
    } catch (error) {
      rollback(this.database);
      throw error;
    }
  }

  discardRegistrationVerification(
    email: string,
    challengeId: string,
    now: number,
  ): void {
    this.database.exec("BEGIN IMMEDIATE");
    try {
      this.database
        .prepare(`
          DELETE FROM registration_email_verifications
          WHERE email_normalized = ? AND challenge_id = ?
        `)
        .run(email, challengeId);
      const previous = this.database
        .prepare(`
          SELECT challenge_id
          FROM registration_email_verifications
          WHERE email_normalized = ? AND active = 0 AND expires_at > ?
          ORDER BY created_at DESC
          LIMIT 1
        `)
        .get(email, now) as { challenge_id: string } | undefined;
      if (previous) {
        this.database
          .prepare(`
            UPDATE registration_email_verifications
            SET active = 1
            WHERE challenge_id = ?
          `)
          .run(previous.challenge_id);
      }
      this.database.exec("COMMIT");
    } catch (error) {
      rollback(this.database);
      throw error;
    }
  }

  private registrationCodeMatches(
    challenge: RegistrationEmailVerificationRow,
    code: string,
  ): boolean {
    const candidateHash = Buffer.from(
      this.registrationCodeHash(
        challenge.email_normalized,
        challenge.challenge_id,
        code,
      ),
      "hex",
    );
    const expectedHash = Buffer.from(challenge.code_hash, "hex");
    return (
      expectedHash.length === candidateHash.length &&
      timingSafeEqual(expectedHash, candidateHash)
    );
  }

  private preflightRegistrationVerification(
    email: string,
    code: string,
    now: number,
  ): string {
    this.assertEmailVerificationConfigured();
    this.database.exec("BEGIN IMMEDIATE");
    try {
      this.database
        .prepare(`
          DELETE FROM registration_email_verifications
          WHERE retain_until <= ?
        `)
        .run(now);
      this.database
        .prepare(`
          UPDATE registration_email_verifications
          SET active = 0
          WHERE active = 1 AND expires_at <= ?
        `)
        .run(now);
      const challenges = this.database
        .prepare(`
          SELECT email_normalized, challenge_id, code_hash, created_at,
                 expires_at, retain_until, last_sent_at, attempt_count,
                 active
          FROM registration_email_verifications
          WHERE email_normalized = ?
          ORDER BY active DESC, created_at DESC
        `)
        .all(email) as unknown as RegistrationEmailVerificationRow[];
      const active = challenges.find(
        (challenge) => Number(challenge.active) === 1,
      );
      const activeMatches =
        active != null && this.registrationCodeMatches(active, code);
      const obsoleteMatches = challenges.some(
        (challenge) =>
          Number(challenge.active) === 0 &&
          this.registrationCodeMatches(challenge, code),
      );
      if (
        active &&
        activeMatches &&
        Number(active.attempt_count) <
          EMAIL_VERIFICATION_MAX_ATTEMPTS
      ) {
        this.database.exec("COMMIT");
        return active.challenge_id;
      }
      if (
        active &&
        !obsoleteMatches &&
        Number(active.attempt_count) <
          EMAIL_VERIFICATION_MAX_ATTEMPTS
      ) {
        this.database
          .prepare(`
            UPDATE registration_email_verifications
            SET attempt_count = attempt_count + 1
            WHERE challenge_id = ? AND active = 1
          `)
          .run(active.challenge_id);
      }
      this.database.exec("COMMIT");
      throw new ApiError(
        "EMAIL_VERIFICATION_REQUIRED",
        "A valid email verification code is required.",
        400,
      );
    } catch (error) {
      rollback(this.database);
      throw error;
    }
  }

  private derivePassword(
    password: string,
    salt: string,
    profile: ScryptProfile,
  ): Promise<Uint8Array> {
    return this.passwordWork.run(() =>
      scryptPassword(password, salt, profile)
    );
  }

  private insertSession(
    user: UserRow,
    now: number,
  ): NewSession {
    const rawSessionToken = sessionToken();
    const rawCsrfToken = csrfToken();
    const expiresAt = now + this.sessionTtlMs;
    this.database
      .prepare(`
        INSERT INTO sessions (
          token_hash, user_id, csrf_token, created_at,
          expires_at, last_seen_at
        ) VALUES (?, ?, ?, ?, ?, ?)
      `)
      .run(
        sha256(rawSessionToken),
        user.id,
        rawCsrfToken,
        now,
        expiresAt,
        now,
      );
    return {
      sessionToken: rawSessionToken,
      csrfToken: rawCsrfToken,
      expiresAt,
      user: publicUser(user),
    };
  }

  async register(
    value: unknown,
    clock: () => number,
  ): Promise<NewSession> {
    const input = inputObject(value);
    assertCurrentPrivacyConsent(input);
    const email = normalizeEmail(input.email);
    const password = validatePassword(input.password);
    this.assertEmailVerificationConfigured();
    const verificationCode =
      typeof input.verificationCode === "string" &&
      /^\d{6}$/.test(input.verificationCode)
        ? input.verificationCode
        : "invalid";
    const challengeId = this.preflightRegistrationVerification(
      email,
      verificationCode,
      clock(),
    );
    const salt = randomBytes(16).toString("hex");
    const passwordHash = Buffer.from(
      await this.derivePassword(
        password,
        salt,
        CURRENT_SCRYPT_PROFILE,
      ),
    ).toString("hex");
    const now = clock();
    const user: UserRow = {
      id: `usr_${randomUUID().replaceAll("-", "")}`,
      email,
      email_normalized: email,
      password_salt: salt,
      password_hash: passwordHash,
      password_hash_version: CURRENT_PASSWORD_HASH_VERSION,
      privacy_consent_version: PRIVACY_CONSENT_VERSION,
      privacy_consent_accepted_at: now,
      email_verified_at: now,
      created_at: now,
    };

    this.database.exec("BEGIN IMMEDIATE");
    try {
      const challenge = this.database
        .prepare(`
          SELECT email_normalized, challenge_id, code_hash, created_at,
                 expires_at, retain_until, last_sent_at, attempt_count,
                 active
          FROM registration_email_verifications
          WHERE email_normalized = ? AND challenge_id = ? AND active = 1
        `)
        .get(
          email,
          challengeId,
        ) as RegistrationEmailVerificationRow | undefined;
      if (
        !challenge ||
        Number(challenge.expires_at) <= now ||
        Number(challenge.attempt_count) >=
          EMAIL_VERIFICATION_MAX_ATTEMPTS ||
        !this.registrationCodeMatches(challenge, verificationCode)
      ) {
        throw new ApiError(
          "EMAIL_VERIFICATION_REQUIRED",
          "A valid email verification code is required.",
          400,
        );
      }
      const consumed = this.database
        .prepare(`
          DELETE FROM registration_email_verifications
          WHERE email_normalized = ?
        `)
        .run(email);
      if (Number(consumed.changes) < 1) {
        throw new ApiError(
          "EMAIL_VERIFICATION_REQUIRED",
          "A valid email verification code is required.",
          400,
        );
      }
      this.database
        .prepare(`
          INSERT INTO users (
            id, email, email_normalized, password_salt,
            password_hash, password_hash_version,
            privacy_consent_version, privacy_consent_accepted_at,
            email_verified_at, created_at, updated_at
          ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        `)
        .run(
          user.id,
          user.email,
          user.email_normalized,
          user.password_salt,
          user.password_hash,
          user.password_hash_version,
          user.privacy_consent_version,
          user.privacy_consent_accepted_at,
          user.email_verified_at,
          now,
          now,
        );
      const session = this.insertSession(user, now);
      this.database.exec("COMMIT");
      return session;
    } catch (error) {
      rollback(this.database);
      if (
        error instanceof Error &&
        /users\.email_normalized|UNIQUE constraint/i.test(error.message)
      ) {
        throw new ApiError(
          "EMAIL_ALREADY_REGISTERED",
          "An account already exists for this email address.",
          409,
        );
      }
      throw error;
    }
  }

  async login(value: unknown, now: number): Promise<NewSession> {
    const input = inputObject(value);
    const email = normalizeEmail(input.email);
    const password =
      typeof input.password === "string" &&
      input.password.length > 0 &&
      input.password.length <= 128
        ? input.password
        : "";
    const row = this.database
      .prepare(`
        SELECT id, email, email_normalized, password_salt,
               password_hash, password_hash_version,
               privacy_consent_version, privacy_consent_accepted_at,
               email_verified_at,
               created_at
        FROM users
        WHERE email_normalized = ?
      `)
      .get(email) as UserRow | undefined;

    const storedVersion = row?.password_hash_version || "";
    const legacy =
      Boolean(row) &&
      (
        !storedVersion ||
        storedVersion === "scrypt-v1" ||
        storedVersion === LEGACY_PASSWORD_HASH_VERSION
      );
    const supported =
      !row ||
      legacy ||
      storedVersion === CURRENT_PASSWORD_HASH_VERSION;
    const verificationProfile =
      row && legacy ? LEGACY_SCRYPT_PROFILE : CURRENT_SCRYPT_PROFILE;
    const candidatePassword =
      password || "invalid-password-placeholder";
    const derived = Buffer.from(
      await this.derivePassword(
        candidatePassword,
        row?.password_salt ||
          "0123456789abcdef0123456789abcdef",
        verificationProfile,
      ),
    );
    const expected = row
      ? Buffer.from(row.password_hash, "hex")
      : Buffer.alloc(SCRYPT_KEY_LENGTH);
    const matches =
      supported &&
      expected.length === derived.length &&
      timingSafeEqual(expected, derived);

    let upgraded:
      | { salt: string; hash: string }
      | undefined;
    if (row && legacy) {
      const upgradeSalt = randomBytes(16).toString("hex");
      // A legacy account always performs one current-cost derivation after the
      // legacy check. This both upgrades successful logins and reduces the
      // timing difference for an incorrect legacy password.
      const upgradeHash = Buffer.from(
        await this.derivePassword(
          matches
            ? password
            : "invalid-password-placeholder",
          upgradeSalt,
          CURRENT_SCRYPT_PROFILE,
        ),
      ).toString("hex");
      if (matches) {
        upgraded = { salt: upgradeSalt, hash: upgradeHash };
      }
    }
    if (!row || !password || !matches) {
      throw new ApiError(
        "INVALID_CREDENTIALS",
        "Email or password is incorrect.",
        401,
      );
    }

    this.database.exec("BEGIN IMMEDIATE");
    try {
      if (upgraded) {
        this.database
          .prepare(`
            UPDATE users
            SET password_salt = ?, password_hash = ?,
                password_hash_version = ?, updated_at = ?
            WHERE id = ?
          `)
          .run(
            upgraded.salt,
            upgraded.hash,
            CURRENT_PASSWORD_HASH_VERSION,
            now,
            row.id,
          );
      }
      this.database
        .prepare("DELETE FROM sessions WHERE expires_at <= ?")
        .run(now);
      const session = this.insertSession(row, now);
      this.database.exec("COMMIT");
      return session;
    } catch (error) {
      rollback(this.database);
      throw error;
    }
  }

  getSession(
    rawSessionToken: string,
    now: number,
  ): AuthenticatedSession | null {
    if (
      !rawSessionToken ||
      rawSessionToken.length > 200 ||
      !/^[A-Za-z0-9_-]+$/.test(rawSessionToken)
    ) {
      return null;
    }
    const tokenHash = sha256(rawSessionToken);
    const row = this.database
      .prepare(`
        SELECT sessions.token_hash, sessions.csrf_token,
               sessions.expires_at, sessions.last_seen_at,
               users.id, users.email, users.email_normalized,
               users.password_salt, users.password_hash,
               users.password_hash_version,
               users.privacy_consent_version,
               users.privacy_consent_accepted_at,
               users.email_verified_at,
               users.created_at
        FROM sessions
        INNER JOIN users ON users.id = sessions.user_id
        WHERE sessions.token_hash = ?
      `)
      .get(tokenHash) as SessionRow | undefined;
    if (!row) return null;
    if (Number(row.expires_at) <= now) {
      this.database
        .prepare("DELETE FROM sessions WHERE token_hash = ?")
        .run(tokenHash);
      return null;
    }
    if (now - Number(row.last_seen_at) >= 5 * 60_000) {
      this.database
        .prepare(`
          UPDATE sessions SET last_seen_at = ?
          WHERE token_hash = ?
        `)
        .run(now, tokenHash);
    }
    return {
      user: publicUser(row),
      csrfToken: row.csrf_token,
      expiresAt: Number(row.expires_at),
    };
  }

  logout(rawSessionToken: string): void {
    if (!rawSessionToken || rawSessionToken.length > 200) return;
    this.database
      .prepare("DELETE FROM sessions WHERE token_hash = ?")
      .run(sha256(rawSessionToken));
  }
}
