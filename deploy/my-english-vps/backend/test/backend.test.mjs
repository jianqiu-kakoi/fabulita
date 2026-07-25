import assert from "node:assert/strict";
import { scryptSync } from "node:crypto";
import { mkdtempSync, rmSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import test from "node:test";

const require = createRequire(import.meta.url);
const {
  LEARNING_BATCH_SCHEMA,
  LEARNING_EVENT_SCHEMA,
} = require("../dist/contracts.js");
const { openDatabase } = require("../dist/database.js");
const {
  CURRENT_PASSWORD_HASH_VERSION,
  PRIVACY_CONSENT_VERSION,
} = require("../dist/auth.js");
const { mergeCurrentState } = require("../dist/merge.js");
const {
  createAppServer,
  loadRuntimeConfig,
} = require("../dist/server.js");
const { SqliteLearningStore } = require("../dist/store.js");

const NOW = 1_780_000_100_000;
const ORIGIN = "https://english.example.test";
const SCOPE = "book:my-english:en";
const EMAIL_VERIFICATION_SECRET =
  "test-only-email-verification-secret-32-bytes";

function fakeScorer() {
  return {
    calls: [],
    async score(input, rubric) {
      this.calls.push({ input, rubric });
      return {
        verdict: "near_miss",
        meaningCorrect: true,
        feedbackZh: "意思正确，补上冠词会更自然。",
        suggestedAnswer: rubric.canonicalAnswer,
        confidence: 0.93,
        issues: ["article"],
        modelVersion: "test-model",
      };
    },
  };
}

async function fixture({
  scoreLimitPerMinute = 10,
  authRateLimits,
  actionRequestsPerMinute,
  learningQuotas,
  llmGlobalLimits,
  registrationEnabled = true,
  emailVerificationEnabled = true,
  emailVerificationSecret = EMAIL_VERIFICATION_SECRET,
  verificationEmailSender,
  passwordWork,
  now = () => NOW,
} = {}) {
  const directory = mkdtempSync(join(tmpdir(), "my-english-vps-test-"));
  const path = join(directory, "learning.sqlite");
  const database = openDatabase(path);
  const scorer = fakeScorer();
  const sentVerificationEmails = [];
  const emailSender =
    verificationEmailSender === false
      ? undefined
      : verificationEmailSender || {
          async sendRegistrationCode(email, code) {
            sentVerificationEmails.push({ email, code });
          },
        };
  const server = createAppServer({
    database,
    allowedOrigins: new Set([ORIGIN]),
    cookieName: "test_session",
    sessionTtlDays: 30,
    scoreLimitPerMinute,
    scorer,
    now,
    authRateLimits,
    actionRequestsPerMinute,
    learningQuotas,
    llmGlobalLimits,
    registrationEnabled,
    emailVerificationEnabled,
    emailVerificationSecret,
    verificationEmailSender: emailSender,
    passwordWork,
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const address = server.address();
  if (!address || typeof address === "string") {
    throw new Error("test server did not expose a TCP address");
  }
  return {
    database,
    scorer,
    sentVerificationEmails,
    path,
    baseUrl: `http://127.0.0.1:${address.port}`,
    async close() {
      await new Promise((resolve) => server.close(resolve));
      database.close();
      rmSync(directory, { recursive: true, force: true });
    },
  };
}

async function api(
  baseUrl,
  path,
  {
    method = "GET",
    body,
    cookie,
    csrf,
    origin = ORIGIN,
    headers = {},
  } = {},
) {
  const requestHeaders = { ...headers };
  if (origin) requestHeaders.Origin = origin;
  if (body !== undefined) requestHeaders["Content-Type"] = "application/json";
  if (cookie) requestHeaders.Cookie = cookie;
  if (csrf) requestHeaders["X-CSRF-Token"] = csrf;
  const response = await fetch(`${baseUrl}${path}`, {
    method,
    headers: requestHeaders,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload = await response.json();
  return { response, payload };
}

function cookieFrom(response) {
  const setCookie = response.headers.get("set-cookie");
  assert.ok(setCookie, "response should set a session cookie");
  return {
    header: setCookie,
    request: setCookie.split(";", 1)[0],
  };
}

function currentPrivacyConsent(overrides = {}) {
  return {
    accepted: true,
    version: PRIVACY_CONSENT_VERSION,
    ...overrides,
  };
}

async function requestVerification(
  app,
  email = "learner@example.com",
  { headers = {}, privacyConsent = currentPrivacyConsent() } = {},
) {
  const result = await api(
    app.baseUrl,
    "/api/auth/verification/request",
    {
      method: "POST",
      headers,
      body: {
        email,
        privacyConsent,
      },
    },
  );
  const normalized = email.trim().toLowerCase();
  const delivery = app.sentVerificationEmails
    .toReversed()
    .find((entry) => entry.email === normalized);
  return {
    ...result,
    code: delivery?.code,
  };
}

async function register(
  app,
  email = "learner@example.com",
  { headers = {} } = {},
) {
  const verification = await requestVerification(app, email, {
    headers,
  });
  assert.equal(verification.response.status, 202);
  assert.match(verification.code, /^\d{6}$/);
  const result = await api(app.baseUrl, "/api/auth/register", {
    method: "POST",
    headers,
    body: {
      email,
      password: "correct horse battery staple",
      privacyConsent: currentPrivacyConsent(),
      verificationCode: verification.code,
    },
  });
  assert.equal(result.response.status, 201);
  assert.equal(result.payload.ok, true);
  return {
    ...result,
    cookie: cookieFrom(result.response),
    csrf: result.payload.csrfToken,
  };
}

function learningEvent(overrides = {}) {
  return {
    schema: LEARNING_EVENT_SCHEMA,
    id: "le:event-1",
    occurredAt: 1_780_000_000_000,
    scope: SCOPE,
    projectId: "my-english",
    language: "en",
    source: "homework",
    action: "answer_checked",
    entityId: "hc-scene-05",
    sessionId: "ls:session",
    attemptId: "la:attempt",
    assignmentId: "hotel-check-in-a1",
    sectionId: "hotel-check-in-roleplay",
    questionType: "text_input",
    prompt: "Ask for the Wi-Fi password.",
    answerMode: "typed",
    submittedAnswer: "What is wifi password",
    expectedAnswers: ["What is the Wi-Fi password?"],
    verdict: "near_miss",
    answerCorrect: false,
    attempt: 1,
    snapshotPersisted: true,
    ...overrides,
  };
}

function syncAction({
  events = [],
  currentState = {},
  baseCheckpointVersion = 0,
} = {}) {
  return {
    action: "syncBatch",
    schema: LEARNING_BATCH_SCHEMA,
    scope: SCOPE,
    events,
    currentState,
    baseCheckpointVersion,
  };
}

function homeworkState(itemId, answer, updatedAt) {
  return {
    rawScopes: {
      homework: {
        assignments: {
          "hotel-check-in-a1": {
            responses: {
              [itemId]: { answer, updatedAt },
            },
            currentItemId: itemId,
            updatedAt,
          },
        },
        updatedAt,
      },
    },
  };
}

test("review recency ignores dueAt so a newer review may schedule an earlier due date", () => {
  const merged = mergeCurrentState(
    {
      rawScopes: {
        review: {
          cards: {
            reservation: {
              lastReviewedAt: 100,
              updatedAt: 100,
              dueAt: 10_000,
              interval: 10,
              reviews: 1,
            },
          },
          updatedAt: 100,
        },
      },
    },
    {
      rawScopes: {
        review: {
          cards: {
            reservation: {
              lastReviewedAt: 200,
              updatedAt: 200,
              dueAt: 500,
              interval: 1,
              reviews: 2,
            },
          },
          updatedAt: 200,
        },
      },
    },
    {
      assignmentResetAt: {},
      questionDeletedAt: {},
    },
  );
  const card = merged.rawScopes.review.cards.reservation;
  assert.equal(card.lastReviewedAt, 200);
  assert.equal(card.dueAt, 500);
  assert.equal(card.interval, 1);
  assert.equal(card.reviews, 2);
});

test("Q&A tombstones delete ties and stale items but allow newer same-id recreation", () => {
  const merged = mergeCurrentState(
    {
      rawScopes: {
        qa: {
          items: [],
          tombstones: {
            "q:recreated": 300,
            "q:tie": 300,
          },
          updatedAt: 300,
        },
      },
    },
    {
      rawScopes: {
        qa: {
          items: [
            {
              id: "q:recreated",
              question: "A genuinely new question",
              createdAt: 301,
              updatedAt: 301,
            },
            {
              id: "q:tie",
              question: "Must remain deleted",
              createdAt: 100,
              updatedAt: 300,
            },
          ],
          updatedAt: 301,
        },
      },
    },
    {
      assignmentResetAt: {},
      questionDeletedAt: {
        "q:recreated": 300,
        "q:tie": 300,
      },
    },
  );
  assert.deepEqual(
    merged.rawScopes.qa.items.map((item) => item.id),
    ["q:recreated"],
  );
  assert.equal(
    merged.rawScopes.qa.items[0].question,
    "A genuinely new question",
  );
  assert.equal(merged.rawScopes.qa.tombstones["q:recreated"], 300);
  assert.equal(merged.rawScopes.qa.tombstones["q:tie"], 300);
});

test("SQLite initializes WAL and all durable tables; health is public", async () => {
  const app = await fixture();
  try {
    const journal = app.database
      .prepare("PRAGMA journal_mode")
      .get();
    assert.equal(String(journal.journal_mode).toLowerCase(), "wal");
    const tables = app.database
      .prepare(`
        SELECT name FROM sqlite_master
        WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
      `)
      .all()
      .map((row) => row.name);
    assert.deepEqual(tables, [
      "auth_rate_limits",
      "learning_checkpoints",
      "learning_events",
      "learning_rate_limits",
      "learning_usage",
      "registration_email_verifications",
      "sessions",
      "users",
    ]);

    const { response, payload } = await api(app.baseUrl, "/api/health", {
      origin: null,
    });
    assert.equal(response.status, 200);
    assert.equal(payload.service, "my-english-api");
    assert.equal(payload.version, "0.2.0");
    assert.equal(payload.registrationEnabled, true);
    assert.equal(payload.emailVerificationEnabled, true);
    assert.equal(payload.privacyConsentVersion, PRIVACY_CONSENT_VERSION);
  } finally {
    await app.close();
  }
});

test("opening a legacy database safely adds consent and hash-version columns", () => {
  const directory = mkdtempSync(join(tmpdir(), "my-english-migration-test-"));
  const path = join(directory, "legacy.sqlite");
  const legacy = new DatabaseSync(path);
  legacy.exec(`
    CREATE TABLE users (
      id TEXT PRIMARY KEY,
      email TEXT NOT NULL,
      email_normalized TEXT NOT NULL UNIQUE,
      password_salt TEXT NOT NULL,
      password_hash TEXT NOT NULL,
      created_at INTEGER NOT NULL,
      updated_at INTEGER NOT NULL
    );
    INSERT INTO users VALUES (
      'legacy-user', 'legacy@example.com', 'legacy@example.com',
      'salt', 'hash', 100, 100
    );
    CREATE TABLE registration_email_verifications (
      email_normalized TEXT PRIMARY KEY,
      challenge_id TEXT NOT NULL,
      code_hash TEXT NOT NULL,
      created_at INTEGER NOT NULL,
      expires_at INTEGER NOT NULL,
      last_sent_at INTEGER NOT NULL,
      attempt_count INTEGER NOT NULL
    );
    INSERT INTO registration_email_verifications VALUES (
      'pending@example.com', 'legacy-challenge', 'legacy-code-hash',
      100, 200, 100, 3
    );
  `);
  legacy.close();

  const migrated = openDatabase(path);
  try {
    const columns = migrated
      .prepare("PRAGMA table_info(users)")
      .all()
      .map((column) => column.name);
    assert.ok(columns.includes("password_hash_version"));
    assert.ok(columns.includes("privacy_consent_version"));
    assert.ok(columns.includes("privacy_consent_accepted_at"));
    assert.ok(columns.includes("email_verified_at"));
    const preserved = migrated
      .prepare(`
        SELECT id, password_hash_version, privacy_consent_version,
               privacy_consent_accepted_at, email_verified_at
        FROM users WHERE id = 'legacy-user'
      `)
      .get();
    assert.equal(preserved.id, "legacy-user");
    assert.equal(preserved.password_hash_version, null);
    assert.equal(preserved.privacy_consent_version, null);
    assert.equal(preserved.privacy_consent_accepted_at, null);
    assert.equal(preserved.email_verified_at, null);
    const verificationColumns = migrated
      .prepare("PRAGMA table_info(registration_email_verifications)")
      .all();
    assert.equal(
      verificationColumns.find(
        (column) => column.name === "challenge_id",
      ).pk,
      1,
    );
    assert.ok(
      verificationColumns.some((column) => column.name === "active"),
    );
    assert.ok(
      verificationColumns.some(
        (column) => column.name === "retain_until",
      ),
    );
    assert.equal(
      migrated
        .prepare(`
          SELECT COUNT(*) AS count
          FROM registration_email_verifications
        `)
        .get().count,
      0,
      "ephemeral challenges from the legacy schema must not survive migration",
    );
  } finally {
    migrated.close();
    rmSync(directory, { recursive: true, force: true });
  }
});

test("registration requires exact current consent and stores server acceptance time", async () => {
  const app = await fixture();
  try {
    const missing = await api(app.baseUrl, "/api/auth/register", {
      method: "POST",
      body: {
        email: "missing@example.com",
        password: "correct horse battery staple",
      },
    });
    assert.equal(missing.response.status, 400);
    assert.equal(missing.payload.code, "PRIVACY_CONSENT_REQUIRED");

    const stale = await api(app.baseUrl, "/api/auth/register", {
      method: "POST",
      body: {
        email: "stale@example.com",
        password: "correct horse battery staple",
        privacyConsent: {
          accepted: true,
          version: "2026-01-01",
        },
      },
    });
    assert.equal(stale.response.status, 400);
    assert.equal(stale.payload.code, "PRIVACY_CONSENT_REQUIRED");
    assert.equal(
      app.database.prepare("SELECT COUNT(*) AS count FROM users").get().count,
      0,
    );

    const verification = await requestVerification(
      app,
      "accepted@example.com",
      {
        privacyConsent: currentPrivacyConsent({
          acceptedAt: 1,
        }),
      },
    );
    assert.equal(verification.response.status, 202);
    const accepted = await api(app.baseUrl, "/api/auth/register", {
      method: "POST",
      body: {
        email: "accepted@example.com",
        password: "correct horse battery staple",
        privacyConsent: currentPrivacyConsent({
          // This untrusted timestamp must never be persisted.
          acceptedAt: 1,
        }),
        verificationCode: verification.code,
      },
    });
    assert.equal(accepted.response.status, 201);
    const row = app.database
      .prepare(`
        SELECT privacy_consent_version, privacy_consent_accepted_at,
               email_verified_at
        FROM users WHERE email_normalized = 'accepted@example.com'
      `)
      .get();
    assert.equal(row.privacy_consent_version, PRIVACY_CONSENT_VERSION);
    assert.equal(row.privacy_consent_accepted_at, NOW);
    assert.equal(row.email_verified_at, NOW);
  } finally {
    await app.close();
  }
});

test("verification request has the exact response, stores only a bound hash, and invalidates resends", async () => {
  let clock = NOW;
  const app = await fixture({
    now: () => clock,
    authRateLimits: {
      verificationIpPerHour: 10,
      verificationEmailPerHour: 10,
      registerIpPerHour: 10,
      registerEmailPerHour: 10,
    },
  });
  try {
    const missingConsent = await api(
      app.baseUrl,
      "/api/auth/verification/request",
      {
        method: "POST",
        body: { email: "learner@example.com" },
      },
    );
    assert.equal(missingConsent.response.status, 400);
    assert.equal(
      missingConsent.payload.code,
      "PRIVACY_CONSENT_REQUIRED",
    );

    const first = await requestVerification(
      app,
      " Learner@Example.COM ",
    );
    assert.equal(first.response.status, 202);
    assert.deepEqual(first.payload, {
      ok: true,
      expiresInSeconds: 600,
      resendAfterSeconds: 60,
    });
    assert.match(first.code, /^\d{6}$/);
    const firstRow = app.database
      .prepare(`
        SELECT email_normalized, challenge_id, code_hash, expires_at,
               attempt_count
        FROM registration_email_verifications
      `)
      .get();
    assert.equal(firstRow.email_normalized, "learner@example.com");
    assert.equal(firstRow.expires_at, NOW + 600_000);
    assert.equal(firstRow.attempt_count, 0);
    assert.notEqual(firstRow.code_hash, first.code);
    assert.doesNotMatch(JSON.stringify(firstRow), new RegExp(first.code));

    const tooSoon = await requestVerification(
      app,
      "learner@example.com",
    );
    assert.equal(tooSoon.response.status, 429);
    assert.equal(tooSoon.payload.code, "VERIFICATION_RATE_LIMITED");
    assert.equal(tooSoon.response.headers.get("retry-after"), "60");

    clock += 61_000;
    const resent = await requestVerification(
      app,
      "learner@example.com",
    );
    assert.equal(resent.response.status, 202);
    const resentRow = app.database
      .prepare(`
        SELECT challenge_id, code_hash, attempt_count
        FROM registration_email_verifications
        WHERE active = 1
      `)
      .get();
    assert.notEqual(resentRow.challenge_id, firstRow.challenge_id);
    assert.notEqual(resent.code, first.code);
    assert.equal(resentRow.attempt_count, 0);
    const retainedOld = app.database
      .prepare(`
        SELECT active, expires_at, retain_until
        FROM registration_email_verifications
        WHERE challenge_id = ?
      `)
      .get(firstRow.challenge_id);
    assert.equal(retainedOld.active, 0);
    assert.equal(retainedOld.expires_at, NOW + 600_000);
    assert.equal(retainedOld.retain_until, NOW + 661_000);

    const obsolete = await api(app.baseUrl, "/api/auth/register", {
      method: "POST",
      body: {
        email: "learner@example.com",
        password: "correct horse battery staple",
        privacyConsent: currentPrivacyConsent(),
        verificationCode: first.code,
      },
    });
    assert.equal(obsolete.response.status, 400);
    assert.equal(
      obsolete.payload.code,
      "EMAIL_VERIFICATION_REQUIRED",
    );
    assert.equal(
      app.database
        .prepare(`
          SELECT attempt_count
          FROM registration_email_verifications
          WHERE email_normalized = 'learner@example.com'
            AND active = 1
        `)
        .get().attempt_count,
      0,
      "an obsolete code must not consume an attempt on the active challenge",
    );

    clock += 539_001;
    const obsoleteAfterOwnExpiry = await api(
      app.baseUrl,
      "/api/auth/register",
      {
        method: "POST",
        body: {
          email: "learner@example.com",
          password: "correct horse battery staple",
          privacyConsent: currentPrivacyConsent(),
          verificationCode: first.code,
        },
      },
    );
    assert.equal(obsoleteAfterOwnExpiry.response.status, 400);
    assert.equal(
      obsoleteAfterOwnExpiry.payload.code,
      "EMAIL_VERIFICATION_REQUIRED",
    );
    assert.equal(
      app.database
        .prepare(`
          SELECT attempt_count
          FROM registration_email_verifications
          WHERE email_normalized = 'learner@example.com'
            AND active = 1
        `)
        .get().attempt_count,
      0,
      "an obsolete code remains recognizable after its own expiry and must not consume the active challenge",
    );

    const accepted = await api(app.baseUrl, "/api/auth/register", {
      method: "POST",
      body: {
        email: "learner@example.com",
        password: "correct horse battery staple",
        privacyConsent: currentPrivacyConsent(),
        verificationCode: resent.code,
      },
    });
    assert.equal(accepted.response.status, 201);
    assert.equal(
      app.database
        .prepare(`
          SELECT COUNT(*) AS count
          FROM registration_email_verifications
        `)
        .get().count,
      0,
    );
  } finally {
    await app.close();
  }
});

test("verification attempts survive resend, obsolete codes do not count, and lock lasts to expiry", async () => {
  let clock = NOW;
  const app = await fixture({
    now: () => clock,
    authRateLimits: {
      verificationIpPerHour: 20,
      verificationEmailPerHour: 20,
      registerIpPerHour: 20,
      registerEmailPerHour: 20,
    },
  });
  try {
    const first = await requestVerification(app, "attempts@example.com");
    const wrongBeforeResend =
      first.code === "999999" ? "888888" : "999999";
    for (let attempt = 1; attempt <= 4; attempt += 1) {
      const rejected = await api(app.baseUrl, "/api/auth/register", {
        method: "POST",
        body: {
          email: "attempts@example.com",
          password: "correct horse battery staple",
          privacyConsent: currentPrivacyConsent(),
          verificationCode: wrongBeforeResend,
        },
      });
      assert.equal(rejected.response.status, 400);
      assert.equal(
        rejected.payload.code,
        "EMAIL_VERIFICATION_REQUIRED",
      );
    }
    assert.equal(
      app.database
        .prepare(`
          SELECT attempt_count
          FROM registration_email_verifications
          WHERE email_normalized = 'attempts@example.com'
            AND active = 1
        `)
        .get().attempt_count,
      4,
    );

    clock += 61_000;
    const resent = await requestVerification(
      app,
      "attempts@example.com",
    );
    assert.equal(resent.response.status, 202);
    assert.notEqual(resent.code, first.code);
    const activeAfterResend = app.database
      .prepare(`
        SELECT challenge_id, attempt_count
        FROM registration_email_verifications
        WHERE email_normalized = 'attempts@example.com'
          AND active = 1
      `)
      .get();
    assert.equal(activeAfterResend.attempt_count, 4);
    assert.equal(
      app.database
        .prepare(`
          SELECT COUNT(*) AS count
          FROM registration_email_verifications
          WHERE email_normalized = 'attempts@example.com'
        `)
        .get().count,
      2,
    );

    const obsolete = await api(app.baseUrl, "/api/auth/register", {
      method: "POST",
      body: {
        email: "attempts@example.com",
        password: "correct horse battery staple",
        privacyConsent: currentPrivacyConsent(),
        verificationCode: first.code,
      },
    });
    assert.equal(obsolete.response.status, 400);
    assert.equal(
      obsolete.payload.code,
      "EMAIL_VERIFICATION_REQUIRED",
    );
    assert.equal(
      app.database
        .prepare(`
          SELECT attempt_count
          FROM registration_email_verifications
          WHERE email_normalized = 'attempts@example.com'
            AND active = 1
        `)
        .get().attempt_count,
      4,
      "the obsolete pre-resend code must not consume the fifth attempt",
    );

    const fifthWrong = [first.code, resent.code, wrongBeforeResend]
      .includes("777777")
      ? "666666"
      : "777777";
    const fifth = await api(app.baseUrl, "/api/auth/register", {
      method: "POST",
      body: {
        email: "attempts@example.com",
        password: "correct horse battery staple",
        privacyConsent: currentPrivacyConsent(),
        verificationCode: fifthWrong,
      },
    });
    assert.equal(fifth.response.status, 400);
    assert.equal(fifth.payload.code, "EMAIL_VERIFICATION_REQUIRED");
    assert.equal(
      app.database
        .prepare(`
          SELECT attempt_count
          FROM registration_email_verifications
          WHERE email_normalized = 'attempts@example.com'
            AND active = 1
        `)
        .get().attempt_count,
      5,
    );

    const lockedResend = await requestVerification(
      app,
      "attempts@example.com",
    );
    assert.equal(lockedResend.response.status, 429);
    assert.equal(
      lockedResend.payload.code,
      "VERIFICATION_RATE_LIMITED",
    );
    assert.equal(
      lockedResend.response.headers.get("retry-after"),
      "600",
    );

    const lockedCorrect = await api(
      app.baseUrl,
      "/api/auth/register",
      {
        method: "POST",
        body: {
          email: "attempts@example.com",
          password: "correct horse battery staple",
          privacyConsent: currentPrivacyConsent(),
          verificationCode: resent.code,
        },
      },
    );
    assert.equal(lockedCorrect.response.status, 400);
    assert.equal(
      lockedCorrect.payload.code,
      "EMAIL_VERIFICATION_REQUIRED",
    );

    clock += 600_001;
    const unlocked = await requestVerification(
      app,
      "attempts@example.com",
    );
    assert.equal(unlocked.response.status, 202);
    assert.equal(
      app.database
        .prepare(`
          SELECT attempt_count
          FROM registration_email_verifications
          WHERE email_normalized = 'attempts@example.com'
            AND active = 1
        `)
        .get().attempt_count,
      0,
    );
    const created = await api(app.baseUrl, "/api/auth/register", {
      method: "POST",
      body: {
        email: "attempts@example.com",
        password: "correct horse battery staple",
        privacyConsent: currentPrivacyConsent(),
        verificationCode: unlocked.code,
      },
    });
    assert.equal(created.response.status, 201);
  } finally {
    await app.close();
  }
});

test("verification is single-use and duplicate insertion rollback preserves the challenge", async () => {
  let clock = NOW;
  const app = await fixture({
    now: () => clock,
    authRateLimits: {
      verificationIpPerHour: 20,
      verificationEmailPerHour: 20,
      registerIpPerHour: 20,
      registerEmailPerHour: 20,
    },
  });
  try {
    const valid = await requestVerification(app, "atomic@example.com");
    const created = await api(app.baseUrl, "/api/auth/register", {
      method: "POST",
      body: {
        email: "atomic@example.com",
        password: "correct horse battery staple",
        privacyConsent: currentPrivacyConsent(),
        verificationCode: valid.code,
      },
    });
    assert.equal(created.response.status, 201);
    const reused = await api(app.baseUrl, "/api/auth/register", {
      method: "POST",
      body: {
        email: "atomic@example.com",
        password: "another correct horse battery staple",
        privacyConsent: currentPrivacyConsent(),
        verificationCode: valid.code,
      },
    });
    assert.equal(reused.response.status, 400);
    assert.equal(
      reused.payload.code,
      "EMAIL_VERIFICATION_REQUIRED",
    );

    clock += 61_000;
    const existing = await requestVerification(app, "atomic@example.com");
    assert.deepEqual(existing.payload, {
      ok: true,
      expiresInSeconds: 600,
      resendAfterSeconds: 60,
    });
    const duplicate = await api(app.baseUrl, "/api/auth/register", {
      method: "POST",
      body: {
        email: "atomic@example.com",
        password: "another correct horse battery staple",
        privacyConsent: currentPrivacyConsent(),
        verificationCode: existing.code,
      },
    });
    assert.equal(duplicate.response.status, 409);
    assert.equal(duplicate.payload.code, "EMAIL_ALREADY_REGISTERED");
    assert.equal(
      app.database
        .prepare(`
          SELECT COUNT(*) AS count
          FROM registration_email_verifications
          WHERE email_normalized = 'atomic@example.com'
        `)
        .get().count,
      1,
      "duplicate insertion rollback must restore the consumed challenge",
    );
  } finally {
    await app.close();
  }
});

test("the same verification challenge can create only one user under concurrent registration", async () => {
  const app = await fixture({
    authRateLimits: {
      verificationIpPerHour: 20,
      verificationEmailPerHour: 20,
      registerIpPerHour: 20,
      registerEmailPerHour: 20,
    },
    passwordWork: {
      concurrency: 2,
      queueLimit: 2,
    },
  });
  try {
    const verification = await requestVerification(
      app,
      "race@example.com",
    );
    const registerWithSameChallenge = () =>
      api(app.baseUrl, "/api/auth/register", {
        method: "POST",
        body: {
          email: "race@example.com",
          password: "correct horse battery staple",
          privacyConsent: currentPrivacyConsent(),
          verificationCode: verification.code,
        },
      });
    const results = await Promise.all([
      registerWithSameChallenge(),
      registerWithSameChallenge(),
    ]);
    assert.deepEqual(
      results.map((result) => result.response.status).sort(),
      [201, 400],
    );
    const rejected = results.find(
      (result) => result.response.status === 400,
    );
    assert.equal(
      rejected.payload.code,
      "EMAIL_VERIFICATION_REQUIRED",
    );
    assert.equal(
      app.database
        .prepare(`
          SELECT COUNT(*) AS count
          FROM users WHERE email_normalized = 'race@example.com'
        `)
        .get().count,
      1,
    );
    assert.equal(
      app.database
        .prepare(`
          SELECT COUNT(*) AS count
          FROM sessions
        `)
        .get().count,
      1,
    );
    assert.equal(
      app.database
        .prepare(`
          SELECT COUNT(*) AS count
          FROM registration_email_verifications
          WHERE email_normalized = 'race@example.com'
        `)
        .get().count,
      0,
    );
  } finally {
    await app.close();
  }
});

test("verification request limits IP and email without storing raw subjects", async () => {
  let clock = NOW;
  const app = await fixture({
    now: () => clock,
    authRateLimits: {
      verificationIpPerHour: 1,
      verificationEmailPerHour: 1,
    },
  });
  try {
    const first = await requestVerification(
      app,
      "limited@example.com",
      { headers: { "X-Forwarded-For": "203.0.113.20" } },
    );
    assert.equal(first.response.status, 202);
    clock += 61_000;
    const emailLimited = await requestVerification(
      app,
      "limited@example.com",
      { headers: { "X-Forwarded-For": "203.0.113.21" } },
    );
    assert.equal(emailLimited.response.status, 429);
    assert.equal(
      emailLimited.payload.code,
      "VERIFICATION_RATE_LIMITED",
    );
    const ipLimited = await requestVerification(
      app,
      "different@example.com",
      { headers: { "X-Forwarded-For": "203.0.113.20" } },
    );
    assert.equal(ipLimited.response.status, 429);
    assert.equal(ipLimited.payload.code, "VERIFICATION_RATE_LIMITED");

    const storedLimits = JSON.stringify(
      app.database
        .prepare(`
          SELECT bucket, subject_hash
          FROM auth_rate_limits
          WHERE bucket LIKE 'verify:%'
        `)
        .all(),
    );
    assert.doesNotMatch(storedLimits, /limited@example\.com/);
    assert.doesNotMatch(storedLimits, /203\.0\.113\.20/);
  } finally {
    await app.close();
  }
});

test("verification requests share persistent global minute, hourly, and daily budgets", async () => {
  const exerciseBudget = async ({
    verificationGlobalPerMinute,
    verificationGlobalPerHour,
    verificationGlobalPerDay,
    blockedBucket,
  }) => {
    const app = await fixture({
      authRateLimits: {
        verificationIpPerHour: 20,
        verificationEmailPerHour: 20,
        verificationGlobalPerMinute,
        verificationGlobalPerHour,
        verificationGlobalPerDay,
      },
    });
    try {
      for (const [index, address] of [
        ["one", "203.0.113.31"],
        ["two", "203.0.113.32"],
      ]) {
        const accepted = await requestVerification(
          app,
          `${index}@example.com`,
          { headers: { "X-Forwarded-For": address } },
        );
        assert.equal(accepted.response.status, 202);
      }
      const blocked = await requestVerification(
        app,
        "three@example.com",
        { headers: { "X-Forwarded-For": "203.0.113.33" } },
      );
      assert.equal(blocked.response.status, 429);
      assert.equal(
        blocked.payload.code,
        "VERIFICATION_RATE_LIMITED",
      );
      const globalRows = app.database
        .prepare(`
          SELECT bucket, request_count
          FROM auth_rate_limits
          WHERE bucket LIKE 'verify:global:%'
          ORDER BY bucket
        `)
        .all()
        .map((row) => ({
          bucket: row.bucket,
          request_count: row.request_count,
        }));
      assert.deepEqual(
        globalRows,
        [
          { bucket: "verify:global:day", request_count: 2 },
          { bucket: "verify:global:hour", request_count: 2 },
          { bucket: "verify:global:minute", request_count: 2 },
        ],
      );
      assert.ok(
        globalRows.some((row) => row.bucket === blockedBucket),
      );
    } finally {
      await app.close();
    }
  };

  await exerciseBudget({
    verificationGlobalPerMinute: 2,
    verificationGlobalPerHour: 10,
    verificationGlobalPerDay: 10,
    blockedBucket: "verify:global:minute",
  });
  await exerciseBudget({
    verificationGlobalPerMinute: 10,
    verificationGlobalPerHour: 2,
    verificationGlobalPerDay: 10,
    blockedBucket: "verify:global:hour",
  });
  await exerciseBudget({
    verificationGlobalPerMinute: 10,
    verificationGlobalPerHour: 10,
    verificationGlobalPerDay: 2,
    blockedBucket: "verify:global:day",
  });
});

test("email verification fails closed when SMTP is absent or delivery fails", async () => {
  const absent = await fixture({ verificationEmailSender: false });
  try {
    const request = await api(
      absent.baseUrl,
      "/api/auth/verification/request",
      {
        method: "POST",
        body: {
          email: "absent@example.com",
          privacyConsent: currentPrivacyConsent(),
        },
      },
    );
    assert.equal(request.response.status, 503);
    assert.equal(
      request.payload.code,
      "EMAIL_VERIFICATION_UNAVAILABLE",
    );
  } finally {
    await absent.close();
  }

  const failing = await fixture({
    verificationEmailSender: {
      async sendRegistrationCode() {
        throw new Error("provider detail must not escape");
      },
    },
  });
  try {
    const request = await api(
      failing.baseUrl,
      "/api/auth/verification/request",
      {
        method: "POST",
        body: {
          email: "failure@example.com",
          privacyConsent: currentPrivacyConsent(),
        },
      },
    );
    assert.equal(request.response.status, 503);
    assert.equal(
      request.payload.code,
      "EMAIL_VERIFICATION_UNAVAILABLE",
    );
    assert.doesNotMatch(
      JSON.stringify(request.payload),
      /provider detail/,
    );
    assert.equal(
      failing.database
        .prepare(`
          SELECT COUNT(*) AS count
          FROM registration_email_verifications
        `)
        .get().count,
      0,
    );
  } finally {
    await failing.close();
  }
});

test("registration is closed unless the server explicitly enables it", async () => {
  const conservative = loadRuntimeConfig({
    ALLOWED_ORIGINS: ORIGIN,
    DATABASE_PATH: "/tmp/not-opened-by-config-test.sqlite",
  });
  assert.equal(conservative.registrationEnabled, false);
  assert.equal(conservative.emailVerificationEnabled, false);
  const closedWithSmtpDefaults = loadRuntimeConfig({
    ALLOWED_ORIGINS: ORIGIN,
    DATABASE_PATH: "/tmp/not-opened-by-config-test.sqlite",
    SMTP_PORT: "465",
    SMTP_SECURE: "true",
    SMTP_FROM: "My English <no-reply@example.test>",
  });
  assert.equal(closedWithSmtpDefaults.smtp, null);
  assert.throws(
    () =>
      loadRuntimeConfig({
        ALLOWED_ORIGINS: ORIGIN,
        DATABASE_PATH: "/tmp/not-opened-by-config-test.sqlite",
        REGISTRATION_ENABLED: "sometimes",
      }),
    /must be true or false/,
  );
  assert.throws(
    () =>
      loadRuntimeConfig({
        ALLOWED_ORIGINS: ORIGIN,
        DATABASE_PATH: "/tmp/not-opened-by-config-test.sqlite",
        REGISTRATION_ENABLED: "true",
      }),
    /Open registration requires EMAIL_VERIFICATION_ENABLED=true/,
  );
  assert.throws(
    () =>
      loadRuntimeConfig({
        ALLOWED_ORIGINS: ORIGIN,
        DATABASE_PATH: "/tmp/not-opened-by-config-test.sqlite",
        EMAIL_VERIFICATION_ENABLED: "true",
        EMAIL_VERIFICATION_SECRET,
        SMTP_HOST: "smtp.example.test",
      }),
    /SMTP configuration is incomplete/,
  );
  const configuredEnvironment = {
    ALLOWED_ORIGINS: ORIGIN,
    DATABASE_PATH: "/tmp/not-opened-by-config-test.sqlite",
    REGISTRATION_ENABLED: "true",
    EMAIL_VERIFICATION_ENABLED: "true",
    EMAIL_VERIFICATION_SECRET,
    SMTP_HOST: "smtp.example.test",
    SMTP_PORT: "465",
    SMTP_SECURE: "true",
    SMTP_USER: "mailer",
    SMTP_PASSWORD: "smtp-password",
    SMTP_FROM: "My English <no-reply@example.test>",
  };
  const configured = loadRuntimeConfig(configuredEnvironment);
  assert.equal(configured.registrationEnabled, true);
  assert.equal(configured.emailVerificationEnabled, true);
  assert.equal(configured.smtp.port, 465);
  assert.equal(configured.smtp.secure, true);
  assert.equal(configured.smtp.maxConcurrency, 2);
  assert.equal(
    configured.authRateLimits.verificationGlobalPerMinute,
    10,
  );
  assert.equal(
    configured.authRateLimits.verificationGlobalPerHour,
    100,
  );
  assert.equal(
    configured.authRateLimits.verificationGlobalPerDay,
    500,
  );
  const boundedSmtp = loadRuntimeConfig({
    ...configuredEnvironment,
    SMTP_MAX_CONCURRENCY: "99",
    AUTH_VERIFICATION_GLOBAL_LIMIT_PER_MINUTE: "3",
    AUTH_VERIFICATION_GLOBAL_LIMIT_PER_HOUR: "7",
    AUTH_VERIFICATION_GLOBAL_LIMIT_PER_DAY: "9",
  });
  assert.equal(boundedSmtp.smtp.maxConcurrency, 2);
  assert.equal(
    boundedSmtp.authRateLimits.verificationGlobalPerMinute,
    3,
  );
  assert.equal(
    boundedSmtp.authRateLimits.verificationGlobalPerHour,
    7,
  );
  assert.equal(
    boundedSmtp.authRateLimits.verificationGlobalPerDay,
    9,
  );

  const app = await fixture({ registrationEnabled: false });
  try {
    const health = await api(app.baseUrl, "/api/health", {
      origin: null,
    });
    assert.equal(health.payload.registrationEnabled, false);
    const verification = await api(
      app.baseUrl,
      "/api/auth/verification/request",
      {
        method: "POST",
        body: {
          email: "closed@example.com",
          privacyConsent: currentPrivacyConsent(),
        },
      },
    );
    assert.equal(verification.response.status, 403);
    assert.equal(verification.payload.code, "REGISTRATION_CLOSED");
    const result = await api(app.baseUrl, "/api/auth/register", {
      method: "POST",
      body: {
        email: "closed@example.com",
        password: "correct horse battery staple",
        privacyConsent: currentPrivacyConsent(),
      },
    });
    assert.equal(result.response.status, 403);
    assert.equal(result.payload.code, "REGISTRATION_CLOSED");
    assert.equal(
      app.database.prepare("SELECT COUNT(*) AS count FROM users").get().count,
      0,
    );
  } finally {
    await app.close();
  }

  const verificationOff = await fixture({
    registrationEnabled: true,
    emailVerificationEnabled: false,
  });
  try {
    const result = await api(
      verificationOff.baseUrl,
      "/api/auth/verification/request",
      {
        method: "POST",
        body: {
          email: "closed@example.com",
          privacyConsent: currentPrivacyConsent(),
        },
      },
    );
    assert.equal(result.response.status, 403);
    assert.equal(result.payload.code, "REGISTRATION_CLOSED");
  } finally {
    await verificationOff.close();
  }
});

test("registration and login are rate-limited by trusted client IP and normalized email", async () => {
  const app = await fixture({
    authRateLimits: {
      registerIpPerHour: 1,
      registerEmailPerHour: 1,
      loginIpPer15Minutes: 20,
      loginEmailPer15Minutes: 2,
    },
  });
  try {
    await register(app);
    const second = await register(
      app,
      "second@example.com",
      { headers: { "X-Forwarded-For": "203.0.113.10" } },
    );
    // The first registration used the direct loopback subject, so this distinct
    // trusted forwarded client receives its own IP bucket.
    assert.equal(second.response.status, 201);

    const thirdVerification = await requestVerification(
      app,
      "third@example.com",
      { headers: { "X-Forwarded-For": "203.0.113.10" } },
    );
    assert.equal(thirdVerification.response.status, 202);
    const sameIpBlocked = await api(
      app.baseUrl,
      "/api/auth/register",
      {
        method: "POST",
        headers: { "X-Forwarded-For": "203.0.113.10" },
        body: {
          email: "third@example.com",
          password: "correct horse battery staple",
          privacyConsent: currentPrivacyConsent(),
          verificationCode: thirdVerification.code,
        },
      },
    );
    assert.equal(sameIpBlocked.response.status, 429);
    assert.equal(sameIpBlocked.payload.code, "AUTH_RATE_LIMITED");
    assert.match(
      sameIpBlocked.response.headers.get("retry-after"),
      /^\d+$/,
    );

    for (const address of ["203.0.113.11", "203.0.113.12"]) {
      const attempt = await api(app.baseUrl, "/api/auth/login", {
        method: "POST",
        headers: { "X-Forwarded-For": address },
        body: {
          email: " LEARNER@example.com ",
          password: "this password is wrong",
        },
      });
      assert.equal(attempt.response.status, 401);
    }
    const emailBlocked = await api(app.baseUrl, "/api/auth/login", {
      method: "POST",
      headers: { "X-Forwarded-For": "203.0.113.13" },
      body: {
        email: "learner@EXAMPLE.com",
        password: "this password is wrong",
      },
    });
    assert.equal(emailBlocked.response.status, 429);
    assert.equal(emailBlocked.payload.code, "AUTH_RATE_LIMITED");

    const stored = JSON.stringify(
      app.database
        .prepare(`
          SELECT bucket, subject_hash FROM auth_rate_limits
          ORDER BY bucket, subject_hash
        `)
        .all(),
    );
    assert.doesNotMatch(stored, /learner@example\.com/i);
    assert.doesNotMatch(stored, /203\.0\.113\./);
  } finally {
    await app.close();
  }
});

test("email/password auth hashes passwords and uses secure session + CSRF controls", async () => {
  let clock = NOW;
  const app = await fixture({ now: () => clock });
  try {
    const untrusted = await api(app.baseUrl, "/api/auth/register", {
      method: "POST",
      origin: "https://attacker.example",
      body: {
        email: "learner@example.com",
        password: "correct horse battery staple",
        privacyConsent: currentPrivacyConsent(),
      },
    });
    assert.equal(untrusted.response.status, 403);
    assert.equal(untrusted.payload.code, "ORIGIN_NOT_ALLOWED");

    const registered = await register(
      app,
      " Learner@Example.COM ",
    );
    assert.equal(registered.payload.user.email, "learner@example.com");
    assert.match(registered.cookie.header, /HttpOnly/i);
    assert.match(registered.cookie.header, /Secure/i);
    assert.match(registered.cookie.header, /SameSite=Lax/i);
    const userRow = app.database
      .prepare(`
        SELECT email_normalized, password_hash, password_salt,
               password_hash_version, privacy_consent_version,
               privacy_consent_accepted_at, email_verified_at
        FROM users
      `)
      .get();
    assert.equal(userRow.email_normalized, "learner@example.com");
    assert.notEqual(
      userRow.password_hash,
      "correct horse battery staple",
    );
    assert.equal(userRow.password_hash.length, 128);
    assert.equal(userRow.password_salt.length, 32);
    assert.equal(
      userRow.password_hash_version,
      CURRENT_PASSWORD_HASH_VERSION,
    );
    assert.equal(
      userRow.privacy_consent_version,
      PRIVACY_CONSENT_VERSION,
    );
    assert.equal(userRow.privacy_consent_accepted_at, NOW);
    assert.equal(userRow.email_verified_at, NOW);
    const sessionRow = app.database
      .prepare("SELECT token_hash FROM sessions")
      .get();
    assert.doesNotMatch(
      registered.cookie.request,
      new RegExp(sessionRow.token_hash),
    );

    const me = await api(app.baseUrl, "/api/auth/me", {
      cookie: registered.cookie.request,
      origin: null,
    });
    assert.equal(me.response.status, 200);
    assert.equal(me.payload.user.email, "learner@example.com");
    assert.equal(me.payload.csrfToken, registered.csrf);

    const noCsrf = await api(app.baseUrl, "/api/action", {
      method: "POST",
      cookie: registered.cookie.request,
      body: { action: "health" },
    });
    assert.equal(noCsrf.response.status, 403);
    assert.equal(noCsrf.payload.code, "CSRF_TOKEN_INVALID");

    clock += 61_000;
    const duplicateVerification = await requestVerification(
      app,
      "learner@example.com",
    );
    assert.equal(duplicateVerification.response.status, 202);
    const duplicate = await api(app.baseUrl, "/api/auth/register", {
      method: "POST",
      body: {
        email: "learner@example.com",
        password: "another secure password",
        privacyConsent: currentPrivacyConsent(),
        verificationCode: duplicateVerification.code,
      },
    });
    assert.equal(duplicate.response.status, 409);
    assert.equal(duplicate.payload.code, "EMAIL_ALREADY_REGISTERED");

    const wrongLogin = await api(app.baseUrl, "/api/auth/login", {
      method: "POST",
      body: {
        email: "learner@example.com",
        password: "this password is wrong",
      },
    });
    assert.equal(wrongLogin.response.status, 401);
    assert.equal(wrongLogin.payload.code, "INVALID_CREDENTIALS");

    const logout = await api(app.baseUrl, "/api/auth/logout", {
      method: "POST",
      cookie: registered.cookie.request,
      csrf: registered.csrf,
      body: {},
    });
    assert.equal(logout.response.status, 200);
    assert.match(
      logout.response.headers.get("set-cookie"),
      /Max-Age=0/i,
    );
    const signedOut = await api(app.baseUrl, "/api/auth/me", {
      cookie: registered.cookie.request,
      origin: null,
    });
    assert.equal(signedOut.payload.user, null);
    assert.equal(signedOut.payload.csrfToken, null);

    const repeatedLogout = await api(app.baseUrl, "/api/auth/logout", {
      method: "POST",
      cookie: registered.cookie.request,
      body: {},
    });
    assert.equal(repeatedLogout.response.status, 200);
    assert.equal(repeatedLogout.payload.ok, true);
  } finally {
    await app.close();
  }
});

test("successful legacy login upgrades the password hash to the current format", async () => {
  const app = await fixture();
  try {
    const password = "legacy password value";
    const salt = "0123456789abcdef0123456789abcdef";
    const legacyHash = scryptSync(password, salt, 64, {
      N: 16_384,
      r: 8,
      p: 1,
      maxmem: 64 * 1024 * 1024,
    }).toString("hex");
    app.database
      .prepare(`
        INSERT INTO users (
          id, email, email_normalized, password_salt, password_hash,
          password_hash_version, privacy_consent_version,
          privacy_consent_accepted_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?)
      `)
      .run(
        "legacy-user",
        "legacy@example.com",
        "legacy@example.com",
        salt,
        legacyHash,
        100,
        100,
      );

    const first = await api(app.baseUrl, "/api/auth/login", {
      method: "POST",
      body: {
        email: "legacy@example.com",
        password,
      },
    });
    assert.equal(first.response.status, 200);
    const upgraded = app.database
      .prepare(`
        SELECT password_salt, password_hash, password_hash_version,
               privacy_consent_version, email_verified_at
        FROM users WHERE id = 'legacy-user'
      `)
      .get();
    assert.equal(
      upgraded.password_hash_version,
      CURRENT_PASSWORD_HASH_VERSION,
    );
    assert.notEqual(upgraded.password_salt, salt);
    assert.notEqual(upgraded.password_hash, legacyHash);
    // Legacy accounts remain usable without inventing a historical consent.
    assert.equal(upgraded.privacy_consent_version, null);
    assert.equal(upgraded.email_verified_at, null);

    const second = await api(app.baseUrl, "/api/auth/login", {
      method: "POST",
      body: {
        email: "legacy@example.com",
        password,
      },
    });
    assert.equal(second.response.status, 200);
    const stable = app.database
      .prepare(`
        SELECT password_hash, password_hash_version
        FROM users WHERE id = 'legacy-user'
      `)
      .get();
    assert.equal(stable.password_hash, upgraded.password_hash);
    assert.equal(
      stable.password_hash_version,
      CURRENT_PASSWORD_HASH_VERSION,
    );
  } finally {
    await app.close();
  }
});

test("password work concurrency rejects excess expensive hashes before memory grows", async () => {
  const app = await fixture({
    passwordWork: {
      concurrency: 1,
      queueLimit: 0,
    },
  });
  try {
    const firstVerification = await requestVerification(
      app,
      "capacity-one@example.com",
    );
    const secondVerification = await requestVerification(
      app,
      "capacity-two@example.com",
    );
    const request = (email, verificationCode) =>
      api(app.baseUrl, "/api/auth/register", {
        method: "POST",
        body: {
          email,
          password: "correct horse battery staple",
          privacyConsent: currentPrivacyConsent(),
          verificationCode,
        },
      });
    const results = await Promise.all([
      request("capacity-one@example.com", firstVerification.code),
      request("capacity-two@example.com", secondVerification.code),
    ]);
    assert.deepEqual(
      results.map((result) => result.response.status).sort(),
      [201, 503],
    );
    const busy = results.find((result) => result.response.status === 503);
    assert.equal(busy.payload.code, "AUTH_CAPACITY_REACHED");
    assert.equal(
      app.database.prepare("SELECT COUNT(*) AS count FROM users").get().count,
      1,
    );
  } finally {
    await app.close();
  }
});

test("authenticated action requests have a durable per-user throttle", async () => {
  const app = await fixture({ actionRequestsPerMinute: 2 });
  try {
    const auth = await register(app);
    const action = () =>
      api(app.baseUrl, "/api/action", {
        method: "POST",
        cookie: auth.cookie.request,
        csrf: auth.csrf,
        body: { action: "health" },
      });
    assert.equal((await action()).response.status, 200);
    assert.equal((await action()).response.status, 200);
    const limited = await action();
    assert.equal(limited.response.status, 429);
    assert.equal(limited.payload.code, "RATE_LIMITED");
  } finally {
    await app.close();
  }
});

test("sync is transactional, idempotent, isolated, and preserves tombstones", async () => {
  const app = await fixture();
  try {
    const auth = await register(app);
    const invoke = (body) =>
      api(app.baseUrl, "/api/action", {
        method: "POST",
        cookie: auth.cookie.request,
        csrf: auth.csrf,
        body,
      });

    const event = learningEvent();
    const first = await invoke(
      syncAction({
        events: [event],
        currentState: homeworkState(
          "hc-scene-05",
          "first answer",
          100,
        ),
      }),
    );
    assert.equal(first.response.status, 200);
    assert.deepEqual(first.payload.acknowledgedEventIds, [event.id]);
    assert.equal(first.payload.checkpointVersion, 1);

    const retry = await invoke(
      syncAction({
        events: [event],
        currentState: homeworkState(
          "hc-scene-05",
          "first answer",
          100,
        ),
      }),
    );
    assert.equal(retry.response.status, 200);
    assert.equal(retry.payload.cursor, first.payload.cursor);
    assert.equal(
      app.database
        .prepare("SELECT COUNT(*) AS count FROM learning_events")
        .get().count,
      1,
    );

    const conflict = await invoke(
      syncAction({
        events: [
          learningEvent({
            id: "le:must-roll-back",
            occurredAt: 1_780_000_000_001,
          }),
          learningEvent({
            submittedAnswer: "changed after the first upload",
          }),
        ],
      }),
    );
    assert.equal(conflict.response.status, 409);
    assert.equal(conflict.payload.code, "EVENT_ID_CONFLICT");
    assert.equal(
      app.database
        .prepare(`
          SELECT COUNT(*) AS count FROM learning_events
          WHERE event_id = 'le:must-roll-back'
        `)
        .get().count,
      0,
    );

    const clientIdentity = await invoke({
      ...syncAction(),
      userId: "attacker-selected-user",
    });
    assert.equal(clientIdentity.response.status, 400);
    assert.equal(
      clientIdentity.payload.code,
      "CLIENT_IDENTITY_NOT_ALLOWED",
    );

    await invoke(
      syncAction({
        events: [
          learningEvent({
            id: "le:item-2",
            entityId: "hc-scene-02",
            occurredAt: 1_780_000_000_002,
          }),
        ],
        currentState: homeworkState(
          "hc-scene-02",
          "second answer",
          102,
        ),
        baseCheckpointVersion: 0,
      }),
    );
    const merged = await invoke({
      action: "bootstrap",
      scope: SCOPE,
    });
    const responses =
      merged.payload.checkpoint.currentState.rawScopes.homework.assignments[
        "hotel-check-in-a1"
      ].responses;
    assert.equal(responses["hc-scene-05"].answer, "first answer");
    assert.equal(responses["hc-scene-02"].answer, "second answer");

    await invoke(
      syncAction({
        events: [
          learningEvent({
            id: "le:reset",
            action: "assignment_reset",
            entityId: "hotel-check-in-a1",
            assignmentId: "hotel-check-in-a1",
            occurredAt: 1_780_000_000_100,
          }),
          learningEvent({
            id: "le:delete-q",
            source: "qa",
            action: "question_deleted",
            entityId: "q:old",
            assignmentId: "",
            occurredAt: 1_780_000_000_101,
          }),
        ],
        currentState: {
          rawScopes: {
            homework: {
              assignments: {
                "hotel-check-in-a1": {
                  responses: {},
                  completedAt: null,
                  updatedAt: 1_780_000_000_100,
                },
              },
            },
            qa: { items: [], updatedAt: 1_780_000_000_101 },
          },
        },
      }),
    );
    await invoke(
      syncAction({
        currentState: {
          ...homeworkState("hc-scene-05", "stale answer", 100),
          rawScopes: {
            ...homeworkState("hc-scene-05", "stale answer", 100)
              .rawScopes,
            qa: {
              items: [
                {
                  id: "q:old",
                  question: "Stale question?",
                  createdAt: 100,
                },
              ],
            },
          },
        },
      }),
    );
    const afterTombstones = await invoke({
      action: "bootstrap",
      scope: SCOPE,
    });
    const state = afterTombstones.payload.checkpoint.currentState;
    assert.deepEqual(
      state.rawScopes.homework.assignments["hotel-check-in-a1"].responses,
      {},
    );
    assert.equal(
      state.rawScopes.homework.assignments["hotel-check-in-a1"].resetAt,
      1_780_000_000_100,
    );
    assert.deepEqual(state.rawScopes.qa.items, []);
    assert.equal(
      state.rawScopes.qa.tombstones["q:old"],
      1_780_000_000_101,
    );
  } finally {
    await app.close();
  }
});

test("bootstrap cursors paginate events and owner keys isolate identical client IDs", async () => {
  const app = await fixture();
  try {
    const store = new SqliteLearningStore(app.database);
    const events = [1, 2, 3].map((number) =>
      learningEvent({
        id: `le:page-${number}`,
        occurredAt: 1_780_000_000_000 + number,
      }),
    );
    await store.syncBatch(
      "owner-a",
      {
        schema: LEARNING_BATCH_SCHEMA,
        scope: SCOPE,
        events,
        currentState: homeworkState("hc-scene-01", "owner A", 100),
        baseCheckpointVersion: 0,
      },
      NOW,
    );
    await store.syncBatch(
      "owner-b",
      {
        schema: LEARNING_BATCH_SCHEMA,
        scope: SCOPE,
        events: [events[0]],
        currentState: homeworkState("hc-scene-01", "owner B", 100),
        baseCheckpointVersion: 0,
      },
      NOW,
    );

    const first = await store.bootstrap("owner-a", SCOPE, "", 2);
    assert.equal(first.events.length, 2);
    assert.equal(first.hasMore, true);
    assert.equal(first.cursor, "c:1:2");
    const second = await store.bootstrap(
      "owner-a",
      SCOPE,
      first.cursor,
      2,
    );
    assert.equal(second.events.length, 1);
    assert.equal(second.events[0].id, "le:page-3");
    assert.equal(second.hasMore, false);
    assert.equal(second.cursor, "c:1:3");

    const ownerB = await store.bootstrap("owner-b", SCOPE, "", 200);
    const answer =
      ownerB.checkpoint.currentState.rawScopes.homework.assignments[
        "hotel-check-in-a1"
      ].responses["hc-scene-01"].answer;
    assert.equal(answer, "owner B");
    assert.equal(ownerB.events.length, 1);
    assert.equal(
      app.database
        .prepare(`
          SELECT COUNT(*) AS count FROM learning_events
          WHERE event_id = 'le:page-1'
        `)
        .get().count,
      2,
    );
  } finally {
    await app.close();
  }
});

test("per-user storage quotas count only new events and rollback overflowing batches", async () => {
  const app = await fixture();
  try {
    const store = new SqliteLearningStore(app.database, {
      maxEventsPerUser: 1,
      maxEventBytesPerUser: 1024 * 1024,
      maxScopesPerUser: 10,
      maxCheckpointBytesPerUser: 1024 * 1024,
    });
    const firstBatch = {
      schema: LEARNING_BATCH_SCHEMA,
      scope: SCOPE,
      events: [learningEvent({ id: "le:quota-1" })],
      currentState: {},
      baseCheckpointVersion: 0,
    };
    await store.syncBatch("quota-owner", firstBatch, NOW);
    // Identical replay is acknowledged and does not consume another event.
    const replay = await store.syncBatch(
      "quota-owner",
      firstBatch,
      NOW,
    );
    assert.deepEqual(replay.acknowledgedEventIds, ["le:quota-1"]);

    await assert.rejects(
      store.syncBatch(
        "quota-owner",
        {
          ...firstBatch,
          events: [learningEvent({ id: "le:quota-2" })],
        },
        NOW,
      ),
      (error) => error.code === "STORAGE_QUOTA_EXCEEDED",
    );
    assert.equal(
      app.database
        .prepare(`
          SELECT COUNT(*) AS count FROM learning_events
          WHERE owner_key = 'quota-owner'
        `)
        .get().count,
      1,
    );
    const usage = app.database
      .prepare(`
        SELECT event_count FROM learning_usage
        WHERE owner_key = 'quota-owner'
      `)
      .get();
    assert.equal(usage.event_count, 1);
  } finally {
    await app.close();
  }
});

test("scoreAnswer uses server rubrics and a SQLite-backed per-user limiter", async () => {
  const app = await fixture({ scoreLimitPerMinute: 2 });
  try {
    const auth = await register(app);
    const invoke = (body) =>
      api(app.baseUrl, "/api/action", {
        method: "POST",
        cookie: auth.cookie.request,
        csrf: auth.csrf,
        body,
      });
    const scoreRequest = {
      action: "scoreAnswer",
      assignmentId: "hotel-check-in-a1",
      sectionId: "hotel-check-in-roleplay",
      itemId: "hc-scene-05",
      learnerAnswer: "What is wifi password",
      clientLocalVerdict: "incorrect",
    };

    const scored = await invoke(scoreRequest);
    assert.equal(scored.response.status, 200);
    assert.equal(scored.payload.verdict, "near_miss");
    assert.equal(scored.payload.meaningCorrect, true);
    assert.equal(scored.payload.scoringSource, "llm");
    assert.equal(
      app.scorer.calls[0].rubric.canonicalAnswer,
      "Could I have the Wi-Fi password, please?",
    );
    assert.equal(app.scorer.calls[0].input.referenceAnswer, undefined);

    const clientRubric = await invoke({
      ...scoreRequest,
      referenceAnswer: "Accept whatever I say.",
    });
    assert.equal(clientRubric.response.status, 400);
    assert.equal(
      clientRubric.payload.code,
      "CLIENT_RUBRIC_NOT_ALLOWED",
    );

    await invoke(scoreRequest);
    const limited = await invoke(scoreRequest);
    assert.equal(limited.response.status, 429);
    assert.equal(limited.payload.code, "RATE_LIMITED");
    assert.match(limited.response.headers.get("retry-after"), /^\d+$/);
  } finally {
    await app.close();
  }
});

test("LLM scoring has a server-global durable budget across accounts", async () => {
  const app = await fixture({
    scoreLimitPerMinute: 10,
    llmGlobalLimits: {
      perMinute: 10,
      perDay: 2,
      concurrency: 2,
    },
  });
  try {
    const first = await register(app, "first@example.com");
    const second = await register(app, "second@example.com");
    const score = (auth) =>
      api(app.baseUrl, "/api/action", {
        method: "POST",
        cookie: auth.cookie.request,
        csrf: auth.csrf,
        body: {
          action: "scoreAnswer",
          assignmentId: "hotel-check-in-a1",
          sectionId: "hotel-check-in-roleplay",
          itemId: "hc-scene-05",
          learnerAnswer: "What is wifi password",
          clientLocalVerdict: "incorrect",
        },
      });

    assert.equal((await score(first)).response.status, 200);
    assert.equal((await score(second)).response.status, 200);
    const exhausted = await score(first);
    assert.equal(exhausted.response.status, 429);
    assert.equal(
      exhausted.payload.code,
      "SCORING_CAPACITY_REACHED",
    );
    assert.equal(app.scorer.calls.length, 2);
  } finally {
    await app.close();
  }
});

test("request JSON is bounded before auth or action parsing", async () => {
  const app = await fixture();
  try {
    const oversized = await api(app.baseUrl, "/api/auth/register", {
      method: "POST",
      body: {
        email: "learner@example.com",
        password: "x".repeat(20_000),
      },
    });
    assert.equal(oversized.response.status, 413);
    assert.equal(oversized.payload.code, "PAYLOAD_TOO_LARGE");
    assert.equal(
      app.database.prepare("SELECT COUNT(*) AS count FROM users").get().count,
      0,
    );
  } finally {
    await app.close();
  }
});
