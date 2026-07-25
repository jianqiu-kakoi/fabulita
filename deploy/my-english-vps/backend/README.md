# My English independent VPS backend

This is the standalone My English API for a Node.js 22.13+ VPS. It has no
CloudBase. HTTP uses `node:http`, durable data uses the built-in `node:sqlite`
module in WAL mode, password hashing uses `crypto.scrypt`, and verification
mail is delivered through a generic SMTP account with Nodemailer.

It is source-complete but intentionally not deployed and contains no
credentials.

## Runtime contract

Run the compiled CommonJS entrypoint:

```sh
node dist/server.js
```

The intended production layout is:

```text
browser -> Cloudflare -> Caddy (HTTPS) -> 127.0.0.1:3000
                                      -> SQLite in /var/lib/my-english
```

Keep Node bound to loopback. Caddy serves the frontend and proxies `/api/*` to
the Node process. The API always issues a host-only cookie with `HttpOnly`,
`Secure`, and `SameSite=Lax`; HTTPS is therefore required outside tests. The
default `__Host-my_english_session` name additionally asks compatible browsers
to enforce the host-only, secure, root-path cookie rules.

Required environment variables:

```text
DATABASE_PATH=/var/lib/my-english/my-english.sqlite
ALLOWED_ORIGINS=https://english.chyuopen.com
```

`ALLOWED_ORIGINS` is a comma-separated list of exact HTTPS origins. Entries
must not contain a path or trailing slash. See `.env.example` for every
optional limit and LLM setting. This program deliberately does not load `.env`
files; systemd should provide `/etc/my-english/my-english.env` through
`EnvironmentFile=`.

The process creates the database parent directory with mode `0750`, sets the
database file to `0600`, enables WAL, foreign keys, a five-second busy timeout,
and creates these tables:

- `users`
- `registration_email_verifications`
- `sessions`
- `auth_rate_limits`
- `learning_events`
- `learning_checkpoints`
- `learning_usage`
- `learning_rate_limits`

Use SQLite's online backup command or stop the service before copying the
database; do not copy only the main file while WAL writes are active.

## Authentication API

All responses are JSON. Login accepts `email` and `password`. Before
registration, request a six-digit email code with the exact server-owned
privacy notice version:

```json
{
  "email": "learner@example.com",
  "privacyConsent": {
    "accepted": true,
    "version": "2026-07-25"
  }
}
```

`POST /api/auth/verification/request` returns HTTP 202 with the same response
whether or not the email already belongs to an account:

```json
{
  "ok": true,
  "expiresInSeconds": 600,
  "resendAfterSeconds": 60
}
```

Registration then carries the delivered code as well as the same explicit
privacy assertion:

```json
{
  "email": "learner@example.com",
  "password": "at least ten characters",
  "verificationCode": "123456",
  "privacyConsent": {
    "accepted": true,
    "version": "2026-07-25"
  }
}
```

Endpoints:

- `GET /api/health` — public process/database health, current consent version,
  and whether registration is open.
- `GET /api/auth/me` — returns `{ "ok": true, "user": null,
  "csrfToken": null }` when signed out; when signed in it returns the public
  user and the session's CSRF token.
- `POST /api/auth/verification/request` — sends a registration code; success
  is HTTP 202 with the fixed expiry and resend delay above.
- `POST /api/auth/register` — creates an account and session; success is HTTP
  201 with `{ok,user,csrfToken}`.
- `POST /api/auth/login` — creates a fresh session; success is HTTP 200 with
  `{ok,user,csrfToken}`.
- `POST /api/auth/logout` — invalidates a valid session and always clears the
  cookie. It is idempotent if the session is already absent or expired.
- `POST /api/action` — authenticated sync/bootstrap/scoring transport.

Every POST requires an exact allowed `Origin`. Authenticated POSTs also require
the latest `csrfToken` in `X-CSRF-Token`. Browser calls must use
`credentials: "include"`.

Registration is fail-closed. `REGISTRATION_ENABLED` and
`EMAIL_VERIFICATION_ENABLED` both default to `false`. The verification request
and registration endpoints return HTTP 403 `REGISTRATION_CLOSED` unless both
are enabled. If registration is enabled without a verification secret of at
least 32 bytes and complete SMTP configuration, startup fails instead of
silently accepting unverified users.

Required verification settings when registration is open:

```text
EMAIL_VERIFICATION_SECRET
SMTP_HOST
SMTP_PORT
SMTP_SECURE
SMTP_USER
SMTP_PASSWORD
SMTP_FROM
```

`SMTP_SECURE=true` provides implicit TLS, normally on port 465. With
`SMTP_SECURE=false`, the transport requires STARTTLS, normally on port 587.
Nodemailer uses a pooled SMTP transport. `SMTP_MAX_CONCURRENCY` defaults to two
connections and is clamped to a maximum of two for this VPS profile.
SMTP delivery or configuration failures return
`EMAIL_VERIFICATION_UNAVAILABLE`; no provider detail is returned to the
browser.

The current consent version is the server constant `2026-07-25`, not an
environment setting. Missing consent, `accepted !== true`, or any other
version returns `PRIVACY_CONSENT_REQUIRED` before password hashing. The
database records that version and the server's request time; a client-supplied
acceptance timestamp is never trusted. Startup safely adds the nullable
consent and `email_verified_at` columns to an existing V0 database, preserving
legacy users without inventing historical consent or verification. New
code-verified registrations store the server verification time.

Codes contain exactly six decimal digits and expire after ten minutes. Only an
HMAC-SHA-256 value is stored; its input binds the registration purpose,
normalized email, random challenge ID, and code. Reissuing after the fixed
60-second cooldown creates a new active challenge and invalidates the old code,
but carries the active failed-attempt count forward. An obsolete retained code
still fails with the generic verification response without consuming an
attempt on the new active challenge. Its HMAC is retained until the current
active challenge expires, independently of the old code's own validity, so a
near-expiry resend cannot turn that old code into a counted guess. Five failed
active attempts lock the email
until that active challenge expires; resending cannot bypass the lock or
produce a usable code during that interval. A valid code is deleted in the same
SQLite transaction that inserts the user and session, so it is single-use
without a consume/create gap.

Verification requests have separate durable limits, by hashed client IP and
hashed normalized email. Defaults are five requests per IP per hour and three
per email per hour. Persistent global SMTP budgets also default to 10 requests
per minute, 100 requests per hour, and 500 requests per day. The IP, email,
global-minute, global-hour, and global-day buckets are checked and consumed
together by the same SQLite-backed authentication limiter, so restarts and
alternate clients do not reset or bypass them. Reissuing a challenge does not
reset those counters. Limit responses use `VERIFICATION_RATE_LIMITED`; missing,
malformed, expired, locked, exhausted, and incorrect codes all use the same
`EMAIL_VERIFICATION_REQUIRED` response.

Passwords are normalized only as passwords (they are never trimmed), must be
10–128 characters, and are stored as a random-salt, explicitly versioned
scrypt hash. New hashes use `N=2^17, r=8, p=1` (about 128 MiB of working
memory). A null/legacy version continues to authenticate with the old
`N=2^14, r=8, p=1` profile and is re-salted and upgraded after a successful
login. Unsupported future versions fail closed.

Expensive password work is globally bounded inside the process. The production
profile permits at most two concurrent scrypt operations and eight queued
requests; queue overflow returns HTTP 503 `AUTH_CAPACITY_REACHED`. The
concurrency parser is clamped to at most two for the 1.6 GB VPS.

Emails are trimmed and lower-cased for uniqueness. Session tokens contain 256
bits of randomness; only their SHA-256 hashes are stored. Session expiry
defaults to 30 days.

Registration and login use separate, SQLite-backed fixed-window limits for the
client IP and normalized email. The backend trusts `X-Forwarded-For` only when
the direct peer is loopback. Caddy must sanitize this header; when Cloudflare
is in front, configure Caddy's trusted proxy/client-IP handling so the header
contains the real client rather than a shared edge IP.

V0 intentionally still has no forgotten-password flow or admin
account-recovery endpoint. Do not promise those features until they are added.

## Learning action API

The browser posts the same stable action contract used by the CloudBase V0:

```json
{
  "action": "syncBatch",
  "schema": "fabulita.learning-sync-batch.v1",
  "scope": "book:my-english:en",
  "baseCheckpointVersion": 3,
  "events": [],
  "currentState": {}
}
```

Supported actions:

- `syncBatch` — at most 40 immutable
  `fabulita.learning-event.v1` events plus the current learning snapshot.
- `bootstrap` — canonical checkpoint plus cursor-paginated immutable events.
- `scoreAnswer` — LLM grading against a server-owned rubric.

Event IDs are idempotency keys. An identical retry is acknowledged without
consuming another event quota; changed content under an existing ID returns
HTTP 409 `EVENT_ID_CONFLICT`. Event inserts, tombstone updates, checkpoint
merge, and usage accounting share one `BEGIN IMMEDIATE` transaction.

Checkpoint merging is item-aware: homework/study responses merge per item,
review schedules per card, favorites by `favoriteUpdatedAt`, and Q&A by
question ID. `assignment_reset` and `question_deleted` create durable
tombstones so stale devices cannot revive old data.

Default per-account ceilings are 20,000 events, 64 MiB of immutable event JSON,
20 scopes, and 8 MiB of aggregate checkpoint JSON. Overflow returns HTTP 413
`STORAGE_QUOTA_EXCEEDED` before insertion and rolls back the whole batch.
Authenticated `/api/action` calls also have a durable per-user limit, default
240 per minute.

The raw HTTP limits are 16 KiB for register/login, 1 KiB for logout, and
1,100,000 bytes for `/api/action`. Contract validation additionally limits a
sync batch to 1 MiB and each merged checkpoint to 1 MiB.

## LLM scoring

The client supplies only exercise IDs, its answer, and its local verdict:

```json
{
  "action": "scoreAnswer",
  "assignmentId": "hotel-check-in-a1",
  "sectionId": "hotel-check-in-roleplay",
  "itemId": "hc-scene-05",
  "learnerAnswer": "What is wifi password",
  "clientLocalVerdict": "incorrect"
}
```

The six hotel check-in rubrics live on the server. Client reference answers,
rubrics, prompts, or intent fields are rejected. Provider output is
schema-checked, remote provider URLs must use HTTPS, and timeouts are bounded.

Set all three values to enable scoring:

```text
LLM_API_KEY
LLM_MODEL
LLM_BASE_URL
```

With credentials unset, sync and authentication still work while
`scoreAnswer` returns `SCORING_NOT_CONFIGURED`. Never put the API key in the
frontend or a repository file.

Cost controls apply at three levels:

- per-account score calls per minute;
- server-global calls per minute and per UTC-aligned 24-hour window;
- in-process concurrent provider calls.

Defaults are 10/account/minute, 30/server/minute, 500/server/day, and four
concurrent calls. Global budgets are SQLite-backed; an attempted provider call
uses budget even if the upstream times out.

## Error contract

HTTP status codes are meaningful and the JSON shape is stable:

```json
{
  "ok": false,
  "code": "AUTHENTICATION_REQUIRED",
  "message": "Sign in before using this endpoint.",
  "error": {
    "code": "AUTHENTICATION_REQUIRED",
    "message": "Sign in before using this endpoint."
  }
}
```

Rate-limit errors also include `retryAfterMs` and an HTTP `Retry-After`
header. Logs intentionally omit bodies, passwords, answers, cookies, provider
responses, and API keys.

## Build and test

Development dependencies are pinned and are used only to compile:

```sh
npm ci --ignore-scripts
npm test
```

`npm test` builds TypeScript and runs HTTP/SQLite integration tests. The tests
cover WAL/schema creation and legacy migration, privacy-consent enforcement,
default-closed registration, versioned scrypt and legacy rehash, password-work
capacity, secure sessions, origin/CSRF enforcement, idempotent logout,
auth/action/global-LLM rate limits, transactional sync, event conflicts and
rollback, owner isolation, cursor pagination, tombstones, storage quotas,
server-owned rubrics, payload bounds, provider output validation, HTTPS
enforcement, and timeout handling.

For a release archive, build first, include `dist/`, and install no runtime
packages:

```sh
npm run build
npm ci --omit=dev --ignore-scripts
node dist/server.js
```
