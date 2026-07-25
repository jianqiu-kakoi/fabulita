# My English CloudBase backend V0

This directory contains one CloudBase function named `my-english-api`. It is
source-complete but intentionally not deployed and contains no credentials.

## Supported actions

The Web SDK calls the same function for every action:

```js
await app.callFunction({
  name: "my-english-api",
  data: { action: "health" },
  parse: true
});
```

The actions are:

- `health` — public process health check.
- `syncBatch` — authenticated, idempotent learning-event upload plus a merged
  checkpoint.
- `bootstrap` — authenticated canonical checkpoint plus cursor-paginated
  immutable events.
- `scoreAnswer` — authenticated LLM grading against a server-owned rubric.

The function resolves the owner from `app.auth.getUserInfo().uid`, with the
trusted CloudBase runtime context as a fallback. It rejects `userId`, `uid`,
`ownerKey`, and similar client fields.

### Sync request

```js
const result = await app.callFunction({
  name: "my-english-api",
  parse: true,
  data: {
    action: "syncBatch",
    schema: "fabulita.learning-sync-batch.v1",
    scope: "book:my-english:en",
    baseCheckpointVersion: 3,
    events: [/* at most 40 fabulita.learning-event.v1 objects */],
    currentState: exportedCurrentState
  }
});
```

Success:

```json
{
  "ok": true,
  "acknowledgedEventIds": ["le:..."],
  "cursor": "c:4:28",
  "checkpointUpdatedAt": 1784937600000
}
```

Event IDs are immutable idempotency keys. Replaying identical content is safe;
reusing an ID with changed content returns `EVENT_ID_CONFLICT`.

The checkpoint merge is intentionally not last-write-wins for the whole
document. Homework and study responses merge per item, Q&A items merge by ID,
review schedules merge per card, and favorites use `favoriteUpdatedAt`.
`assignment_reset` and `question_deleted` events create server tombstones so a
stale device cannot revive old answers or deleted questions.

### Bootstrap request

```js
const page = await app.callFunction({
  name: "my-english-api",
  parse: true,
  data: {
    action: "bootstrap",
    scope: "book:my-english:en",
    cursor: "c:3:20"
  }
});
```

Success:

```json
{
  "ok": true,
  "scope": "book:my-english:en",
  "cursor": "c:4:28",
  "checkpoint": {
    "currentState": {},
    "updatedAt": 1784937600000,
    "version": 4
  },
  "events": [],
  "hasMore": false
}
```

After every `syncBatch`, the client should call `bootstrap` with its previous
cursor, apply the canonical checkpoint, append new immutable events, and repeat
while `hasMore` is true. A cursor covers both checkpoint version and event
sequence, because a draft-only checkpoint can change without creating an event.

### Score request

The client supplies only stable content IDs and its answer. It cannot submit a
reference answer, rubric, prompt, or intent:

```js
const score = await app.callFunction({
  name: "my-english-api",
  parse: true,
  data: {
    action: "scoreAnswer",
    assignmentId: "hotel-check-in-a1",
    sectionId: "hotel-check-in-roleplay",
    itemId: "hc-scene-05",
    learnerAnswer: "What is wifi password",
    clientLocalVerdict: "incorrect"
  }
});
```

Success includes:

```json
{
  "ok": true,
  "verdict": "near_miss",
  "meaningCorrect": true,
  "feedbackZh": "意思正确，补上冠词会更自然。",
  "suggestedAnswer": "What is the Wi-Fi password?",
  "scoringSource": "llm",
  "modelVersion": "configured-model",
  "rubricVersion": "my-english-hotel-check-in-2026-07-25"
}
```

The V0 server rubric covers the six `hotel-check-in-a1` role-play questions.
Provider credentials are read only inside the function. Requests have a bounded
timeout, provider output is schema-checked, and a database-backed per-user
fixed-window limiter defaults to ten score calls per minute.

## CloudBase preparation

Create these document-database collections and set them to **admin-only
read/write**. The browser should use the function, never direct database access:

- `learning_events`
- `learning_checkpoints`
- `learning_rate_limits`

Create a compound ascending index on:

```text
learning_events: ownerKey, scope, sequence
```

Configure function environment variables in the CloudBase console:

```text
LLM_API_KEY                  required for scoreAnswer
LLM_MODEL                    required for scoreAnswer
LLM_BASE_URL                 required HTTPS OpenAI-compatible API base URL
LLM_TIMEOUT_MS               optional, clamped to 1000..20000, default 4000
LLM_RATE_LIMIT_PER_MINUTE    optional, clamped to 1..60, default 10
```

Do not put the key in `cloudbaserc.json`, frontend code, or Git.
For a mainland launch, choose the model provider deliberately and disclose it
in the privacy notice. The function sends only the exercise rubric and the
learner answer to that provider; it never sends the phone number or CloudBase
UID.

## Local verification and later deployment

From `backend/`, after installing dependencies:

```sh
npm test
```

The repository-level CloudBase configuration does not hard-code an environment.
Build first and pass the target explicitly:

```sh
npm run build
cd ..
tcb fn deploy my-english-api -e your-environment-id
```

Deployment, auth-provider enablement, database permissions, indexes, and secrets
are deliberate operator steps and are not performed by this V0 implementation.
