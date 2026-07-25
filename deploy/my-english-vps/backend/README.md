# My English independent VPS backend

This is the standalone My English API for a Node.js 22.13+ VPS. It has no
CloudBase. HTTP uses `node:http`, durable data uses the built-in `node:sqlite`
module in WAL mode, password hashing uses `crypto.scrypt`, and registration is
gated by locally generated one-time invite codes. No SMTP service is required.

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
- `registration_invites`
- `sessions`
- `auth_rate_limits`
- `learning_events`
- `learning_checkpoints`
- `learning_usage`
- `learning_rate_limits`

Use SQLite's online backup command or stop the service before copying the
database; do not copy only the main file while WAL writes are active.

## Authentication and invite API

Login accepts `email` and `password`. Registration requires the exact body:

```json
{
  "displayName": "Learner",
  "email": "learner@example.com",
  "password": "at least ten characters",
  "inviteCode": "ME-XXXXX-XXXXX-XXXXX-XXXXX-XXXXXX",
  "privacyConsent": {
    "accepted": true,
    "version": "2026-07-25"
  }
}
```

Endpoints:

- `GET /api/health` — public health, consent version, and registration flag.
- `GET /api/auth/me` — current public user and CSRF token, or nulls.
- `POST /api/auth/register` — invite-only account and session creation.
- `POST /api/auth/login` — creates a fresh session.
- `POST /api/auth/logout` — idempotently clears the session.
- `POST /api/action` — authenticated learning sync/scoring transport.

Every POST requires an exact allowed `Origin`. Authenticated POSTs also require
the latest `csrfToken` in `X-CSRF-Token`; browser calls use
`credentials: "include"`.

`REGISTRATION_ENABLED` defaults to `false`. Opening registration has no SMTP
dependency, but every registration still needs an available invite. Missing,
malformed, unknown, expired, revoked, consumed, and email-mismatched invites
all return HTTP 400 `INVITE_INVALID_OR_USED`; their state is not disclosed.
Invalid display names return `INVALID_DISPLAY_NAME`. Names are trimmed, must
contain 1–80 Unicode code points, and may not contain ASCII control characters.

Invite payloads use 16 CSPRNG bytes (128 bits), displayed as 26 base32
characters after `ME-`. SQLite stores only SHA-256 of the normalized code.
Invites can be bound to a normalized email, default to 30 days, are grouped by
auditable `batch_id`, carry `secret_version`, and can be revoked. Registration
does a cheap invite preflight before scrypt, then rechecks the same invite ID in
`BEGIN IMMEDIATE`; user insertion, invite consumption, and session creation
commit atomically. Concurrent use can therefore create only one account.

Build first, then create one or more codes against the same SQLite database:

```sh
npm run build
DATABASE_PATH=/var/lib/my-english/my-english.sqlite \
  node dist/invite-cli.js create --count 3

# Optional email binding and TTL:
DATABASE_PATH=/var/lib/my-english/my-english.sqlite \
  node dist/invite-cli.js create --email learner@example.com --days 30
```

Codes are printed once, one per stdout line; only hashes remain in SQLite. The
non-secret batch ID is printed to stderr and can revoke unused codes:

```sh
DATABASE_PATH=/var/lib/my-english/my-english.sqlite \
  node dist/invite-cli.js revoke --batch-id invb_EXAMPLE
```

The current consent version is the server constant `2026-07-25`. Missing or
stale consent returns `PRIVACY_CONSENT_REQUIRED` before password hashing. The
database stores the server acceptance time. Existing accounts receive nullable
`display_name` during migration and continue to log in normally.

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
