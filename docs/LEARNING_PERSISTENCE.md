# Learning persistence contract

Mi Español uses an offline-first persistence boundary. The generated page keeps
current-state snapshots for fast resume and appends every meaningful learner
action to a local event store. When browser storage is available, those events
survive reloads. If a write fails (for example, because browser storage is full),
the page keeps the event in memory, marks the failure in the UI/export, and the
learner should export before closing the tab.

## Client interface

The browser runtime exposes these operations through `learningPersistence`:

```js
learningPersistence.loadSnapshot(key, fallback)
learningPersistence.saveSnapshot(key, value)
learningPersistence.inspectSnapshot(key)
learningPersistence.removeSnapshot(key)
learningPersistence.appendEvent(event)
learningPersistence.listEvents()
learningPersistence.setTransport({ pushBatch(batch) })
await learningPersistence.flush()
learningPersistence.exportAll()
```

Production snapshot and event code calls this interface instead of calling
`localStorage` directly. The default synchronous storage adapter is
`browser-local-v1`; a compatible adapter can be supplied at boot as
`window.fabulitaLearningStorageAdapter`. The live facade is available as
`window.fabulitaLearningPersistence`.

No network transport is configured by default. `flush()` retries pending local
event writes and returns a promise with `local_only`; it does not transmit data.
An authenticated host can register an asynchronous `pushBatch(batch)` transport
without changing answer flows. Existing V1 snapshot keys remain compatible:

- `fabulita.review.v1`
- `fabulita.review.events.v1`
- `fabulita.homework.v1`
- `fabulita.homework.study.v1`
- `fabulita.qa.v1`

New immutable events are stored under `fabulita.learning.events.v1`. Ordinary
homework drafts update their snapshot but do not create events; other answer
forms keep drafts in page memory until submission. Checking an answer, revealing
an answer, rating recall, completing or resetting an assignment, and creating or
deleting a Q&A item each create an event.

## Event envelope

Each event uses `fabulita.learning-event.v1` and includes:

```json
{
  "schema": "fabulita.learning-event.v1",
  "id": "le:uuid",
  "occurredAt": 1784760000000,
  "scope": "book:mi-espanol:es",
  "projectId": "mi-espanol",
  "language": "es",
  "source": "review",
  "action": "answer_checked",
  "entityId": "w:inteligente",
  "sessionId": "rs:uuid",
  "attemptId": "la:uuid",
  "assignmentId": "",
  "sectionId": "",
  "questionType": "",
  "prompt": "",
  "word": "inteligente",
  "answerMode": "typed",
  "submittedAnswer": "smart",
  "expectedAnswers": ["聪明的", "intelligent", "smart"],
  "verdict": "correct",
  "answerCorrect": true,
  "rating": "",
  "attempt": 1,
  "latencyMs": 2500,
  "snapshotPersisted": true
}
```

Event IDs are idempotency keys. Rechecking the same question intentionally
creates a new event and does not overwrite prior attempts. Resetting progress
removes the current snapshot but preserves the event history.

Automatic answer results and self-ratings are separate facts:

- `answer_checked` / `answer_revealed` contain the submitted answer and verdict.
- `self_rated` contains the learner's rating.
- Both share an `attemptId`; analysis counts verdicts from answer events only.

The full JSON export also includes raw current-scope snapshot records. This keeps
answers for assignments, items, or words that were renamed or removed by a later
content version, even when the current UI can no longer render them.

Q&A deletion removes a question from the current list but does not erase the
earlier `question_created` audit event. The delete event contains only the
question ID, not another copy of the question text.

## Future authenticated backend

Cloud persistence is intentionally not active yet. Adding it requires a trusted
user identity and ownership checks; a public anonymous write endpoint would
mix or expose learner data.

The registered transport receives `fabulita.learning-sync-batch.v1`, containing
idempotent events plus the current snapshot bundle. A hosted implementation
should map it to authenticated endpoints such as:

```text
POST /api/v1/learning-sync/batch
PUT  /api/v1/learning-checkpoints/{surface}/{entityId}
GET  /api/v1/learning/bootstrap?scope={scope}&cursor={cursor}
```

`POST /api/v1/learning-sync/batch` accepts:

```json
{
  "schema": "fabulita.learning-sync-batch.v1",
  "scope": "book:mi-espanol:es",
  "events": [],
  "currentState": {}
}
```

The server derives the owner from its authenticated session, never from a
client-supplied user ID. It stores events idempotently by `(owner_key,
event_id)` and returns acknowledged event IDs plus a cursor. A D1
implementation should index `(owner_key, project_id, occurred_at)`.

Until that transport exists, the local event store and the “导出全部记录” JSON file are
the recovery and AI-analysis boundary. Old homework and study snapshots are
included in exports, but historical attempts overwritten before this event
feature cannot be reconstructed. The local V0 is intended for one active tab;
simultaneous writes from several tabs are not yet a supported synchronization
mode.
