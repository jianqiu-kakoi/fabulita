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
  passwordWork,
} = {}) {
  const directory = mkdtempSync(join(tmpdir(), "my-english-vps-test-"));
  const path = join(directory, "learning.sqlite");
  const database = openDatabase(path);
  const scorer = fakeScorer();
  const server = createAppServer({
    database,
    allowedOrigins: new Set([ORIGIN]),
    cookieName: "test_session",
    sessionTtlDays: 30,
    scoreLimitPerMinute,
    scorer,
    now: () => NOW,
    authRateLimits,
    actionRequestsPerMinute,
    learningQuotas,
    llmGlobalLimits,
    registrationEnabled,
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

async function register(baseUrl, email = "learner@example.com") {
  const result = await api(baseUrl, "/api/auth/register", {
    method: "POST",
    body: {
      email,
      password: "correct horse battery staple",
      privacyConsent: currentPrivacyConsent(),
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
    const preserved = migrated
      .prepare(`
        SELECT id, password_hash_version, privacy_consent_version,
               privacy_consent_accepted_at
        FROM users WHERE id = 'legacy-user'
      `)
      .get();
    assert.equal(preserved.id, "legacy-user");
    assert.equal(preserved.password_hash_version, null);
    assert.equal(preserved.privacy_consent_version, null);
    assert.equal(preserved.privacy_consent_accepted_at, null);
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

    const accepted = await api(app.baseUrl, "/api/auth/register", {
      method: "POST",
      body: {
        email: "accepted@example.com",
        password: "correct horse battery staple",
        privacyConsent: currentPrivacyConsent({
          // This untrusted timestamp must never be persisted.
          acceptedAt: 1,
        }),
      },
    });
    assert.equal(accepted.response.status, 201);
    const row = app.database
      .prepare(`
        SELECT privacy_consent_version, privacy_consent_accepted_at
        FROM users WHERE email_normalized = 'accepted@example.com'
      `)
      .get();
    assert.equal(row.privacy_consent_version, PRIVACY_CONSENT_VERSION);
    assert.equal(row.privacy_consent_accepted_at, NOW);
  } finally {
    await app.close();
  }
});

test("registration is closed unless the server explicitly enables it", async () => {
  const conservative = loadRuntimeConfig({
    ALLOWED_ORIGINS: ORIGIN,
    DATABASE_PATH: "/tmp/not-opened-by-config-test.sqlite",
  });
  assert.equal(conservative.registrationEnabled, false);
  assert.throws(
    () =>
      loadRuntimeConfig({
        ALLOWED_ORIGINS: ORIGIN,
        DATABASE_PATH: "/tmp/not-opened-by-config-test.sqlite",
        REGISTRATION_ENABLED: "sometimes",
      }),
    /must be true or false/,
  );

  const app = await fixture({ registrationEnabled: false });
  try {
    const health = await api(app.baseUrl, "/api/health", {
      origin: null,
    });
    assert.equal(health.payload.registrationEnabled, false);
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
    await register(app.baseUrl);
    const registrationBlocked = await api(
      app.baseUrl,
      "/api/auth/register",
      {
        method: "POST",
        headers: { "X-Forwarded-For": "203.0.113.10" },
        body: {
          email: "second@example.com",
          password: "correct horse battery staple",
          privacyConsent: currentPrivacyConsent(),
        },
      },
    );
    // The first registration used the direct loopback subject, so this distinct
    // trusted forwarded client receives its own IP bucket.
    assert.equal(registrationBlocked.response.status, 201);

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
  const app = await fixture();
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
      app.baseUrl,
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
               privacy_consent_accepted_at
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

    const duplicate = await api(app.baseUrl, "/api/auth/register", {
      method: "POST",
      body: {
        email: "learner@example.com",
        password: "another secure password",
        privacyConsent: currentPrivacyConsent(),
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
               privacy_consent_version
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
    const request = (email) =>
      api(app.baseUrl, "/api/auth/register", {
        method: "POST",
        body: {
          email,
          password: "correct horse battery staple",
          privacyConsent: currentPrivacyConsent(),
        },
      });
    const results = await Promise.all([
      request("capacity-one@example.com"),
      request("capacity-two@example.com"),
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
    const auth = await register(app.baseUrl);
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
    const auth = await register(app.baseUrl);
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
    const auth = await register(app.baseUrl);
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
    const first = await register(app.baseUrl, "first@example.com");
    const second = await register(app.baseUrl, "second@example.com");
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
