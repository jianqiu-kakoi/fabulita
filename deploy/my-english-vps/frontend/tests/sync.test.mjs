import assert from "node:assert/strict";
import test from "node:test";

import {
  STORAGE_KEYS,
  claimGuestProgress,
  createLearningCloudBridge,
  learningScopes,
  mergeRemoteLearningState,
  profileStorageKey,
  readBootstrapCursor,
  userStorageProfile,
  writeBootstrapCursor,
} from "../src/sync.js";

class MemoryStorage {
  constructor(entries = {}) {
    this.values = new Map(
      Object.entries(entries).map(([key, value]) => [key, String(value)]),
    );
  }

  getItem(key) {
    return this.values.has(key) ? this.values.get(key) : null;
  }

  setItem(key, value) {
    this.values.set(key, String(value));
  }
}

const config = {
  name: "my-english",
  lang: "en",
  history_id: "my-english",
  review_id: "my-english-core-v1",
  homework_id: "my-english",
  qa_id: "my-english",
};

const scopes = learningScopes(config);

function storedRoot(storage, key) {
  return JSON.parse(storage.getItem(key));
}

function scopeRoot(scope, value) {
  return JSON.stringify({
    version: 1,
    scopes: {
      [scope]: value,
    },
  });
}

function mergeCheckpoint(storage, rawScopes, events = []) {
  return mergeRemoteLearningState({
    storage,
    config,
    checkpoint: {
      currentState: {
        rawScopes,
      },
    },
    events,
  });
}

test("user profiles create stable, isolated storage namespaces", () => {
  const first = userStorageProfile(" user@example.com ");
  const second = userStorageProfile("user+other@example.com");

  assert.equal(first, "user:user_example.com");
  assert.equal(second, "user:user_other_example.com");
  assert.notEqual(
    profileStorageKey(first, STORAGE_KEYS.review),
    profileStorageKey(second, STORAGE_KEYS.review),
  );
  assert.equal(
    profileStorageKey("guest", STORAGE_KEYS.review),
    STORAGE_KEYS.review,
  );
  assert.throws(() => userStorageProfile(""), /用户标识/);
});

test("guest progress is claimed by the first account only", () => {
  const guestReview = scopeRoot(scopes.review, {
    cards: { concierge: { reviews: 2, updatedAt: 200 } },
    updatedAt: 200,
  });
  const storage = new MemoryStorage({
    [STORAGE_KEYS.review]: guestReview,
    [STORAGE_KEYS.learningEvents]: scopeRoot(scopes.history, {
      events: [{ id: "le:guest", occurredAt: 200 }],
      updatedAt: 200,
    }),
    [STORAGE_KEYS.learningSync]: scopeRoot(scopes.history, {
      migrationVersion: 1,
      seededAt: 200,
      events: [{ id: "le:guest", occurredAt: 200 }],
      acknowledgedEventIds: [],
      acknowledgedStateMarker: "",
      updatedAt: 200,
    }),
  });
  writeBootstrapCursor(storage, scopes.history, "guest-cursor-must-stay-guest");
  const firstProfile = userStorageProfile("first-user");
  const secondProfile = userStorageProfile("second-user");

  assert.equal(claimGuestProgress(storage, firstProfile), true);
  assert.equal(
    storage.getItem(profileStorageKey(firstProfile, STORAGE_KEYS.review)),
    guestReview,
  );
  assert.ok(
    storage.getItem(
      profileStorageKey(firstProfile, STORAGE_KEYS.learningEvents),
    ),
  );
  assert.equal(
    storage.getItem(
      profileStorageKey(firstProfile, STORAGE_KEYS.learningSync),
    ),
    storage.getItem(STORAGE_KEYS.learningSync),
  );
  assert.equal(
    storage.getItem(
      profileStorageKey(
        firstProfile,
        "fabulita.learning.bootstrap.v1",
      ),
    ),
    null,
    "guest bootstrap cursors must not cross the account boundary",
  );

  storage.setItem(
    STORAGE_KEYS.learningEvents,
    scopeRoot(scopes.history, {
      events: [
        { id: "le:guest", occurredAt: 200 },
        { id: "le:after-logout", occurredAt: 300 },
      ],
      updatedAt: 300,
    }),
  );
  storage.setItem(
    STORAGE_KEYS.learningSync,
    scopeRoot(scopes.history, {
      migrationVersion: 1,
      seededAt: 200,
      events: [
        { id: "le:guest", occurredAt: 200 },
        { id: "le:after-logout", occurredAt: 300 },
      ],
      acknowledgedEventIds: [],
      acknowledgedStateMarker: "",
      updatedAt: 300,
    }),
  );
  storage.setItem(
    profileStorageKey(firstProfile, STORAGE_KEYS.learningSync),
    scopeRoot(scopes.history, {
      migrationVersion: 1,
      seededAt: 200,
      events: [],
      acknowledgedEventIds: ["le:guest"],
      acknowledgedStateMarker: "state-before-new-guest-progress",
      updatedAt: 250,
    }),
  );

  assert.equal(claimGuestProgress(storage, firstProfile), true);
  const mergedAudit = storedRoot(
    storage,
    profileStorageKey(firstProfile, STORAGE_KEYS.learningEvents),
  ).scopes[scopes.history];
  const mergedOutbox = storedRoot(
    storage,
    profileStorageKey(firstProfile, STORAGE_KEYS.learningSync),
  ).scopes[scopes.history];
  assert.deepEqual(
    mergedAudit.events.map((event) => event.id),
    ["le:after-logout", "le:guest"],
    "the same account should merge immutable guest history on a later claim",
  );
  assert.deepEqual(
    mergedOutbox.events.map((event) => event.id),
    ["le:after-logout"],
    "already acknowledged events stay out while new guest work is queued",
  );
  assert.deepEqual(mergedOutbox.acknowledgedEventIds, ["le:guest"]);
  assert.equal(
    mergedOutbox.acknowledgedStateMarker,
    "",
    "new guest state must invalidate the account checkpoint marker",
  );
  assert.equal(claimGuestProgress(storage, firstProfile), false);

  assert.equal(claimGuestProgress(storage, secondProfile), false);
  assert.equal(
    storage.getItem(profileStorageKey(secondProfile, STORAGE_KEYS.review)),
    null,
  );
});

test("learning events merge by id and keep the newest copy", () => {
  const storage = new MemoryStorage({
    [STORAGE_KEYS.learningEvents]: scopeRoot(scopes.history, {
      events: [
        { id: "le:same", occurredAt: 100, verdict: "incorrect" },
        { id: "le:local", occurredAt: 300 },
      ],
      updatedAt: 300,
    }),
  });

  const changed = mergeCheckpoint(storage, {}, [
    { id: "le:same", occurredAt: 200, verdict: "near_miss" },
    { id: "le:remote", occurredAt: 250 },
  ]);
  const events =
    storedRoot(storage, STORAGE_KEYS.learningEvents).scopes[scopes.history]
      .events;

  assert.equal(changed, true);
  assert.deepEqual(
    events.map((event) => event.id),
    ["le:local", "le:remote", "le:same"],
  );
  assert.equal(
    events.find((event) => event.id === "le:same").verdict,
    "near_miss",
  );
});

test("remote state merges through the iframe adapter read/write contract", () => {
  const values = new Map();
  const writes = [];
  const adapter = {
    read(key) {
      return values.has(key) ? values.get(key) : null;
    },
    write(key, value) {
      writes.push({ key, value });
      values.set(key, String(value));
    },
  };
  const remoteReview = {
    cards: {
      reservation: {
        lastReviewedAt: 500,
        dueAt: 900,
        reviews: 1,
      },
    },
    updatedAt: 500,
  };

  const changed = mergeRemoteLearningState({
    storage: adapter,
    config,
    checkpoint: {
      currentState: {
        rawScopes: {
          review: remoteReview,
        },
      },
    },
  });

  assert.equal(changed, true);
  assert.equal(writes.length, 1);
  assert.equal(writes[0].key, STORAGE_KEYS.review);
  assert.deepEqual(
    JSON.parse(adapter.read(STORAGE_KEYS.review)).scopes[scopes.review],
    remoteReview,
  );
});

test("homework assignments merge responses item by item", () => {
  const storage = new MemoryStorage({
    [STORAGE_KEYS.homework]: scopeRoot(scopes.homework, {
      assignments: {
        "hotel-check-in-a1": {
          currentItemId: "local-current",
          responses: {
            greeting: { answer: "Hello", updatedAt: 300 },
            wifi: { answer: "Local Wi-Fi", updatedAt: 100 },
          },
          updatedAt: 300,
        },
      },
      updatedAt: 300,
    }),
  });

  mergeCheckpoint(storage, {
    homework: {
      assignments: {
        "hotel-check-in-a1": {
          currentItemId: "remote-current",
          responses: {
            greeting: { answer: "Hi", updatedAt: 200 },
            wifi: { answer: "Remote Wi-Fi", updatedAt: 400 },
            checkout: { answer: "At eleven", updatedAt: 350 },
          },
          updatedAt: 400,
        },
      },
      updatedAt: 400,
    },
  });

  const assignment =
    storedRoot(storage, STORAGE_KEYS.homework).scopes[scopes.homework]
      .assignments["hotel-check-in-a1"];
  assert.equal(assignment.currentItemId, "remote-current");
  assert.equal(assignment.responses.greeting.answer, "Hello");
  assert.equal(assignment.responses.wifi.answer, "Remote Wi-Fi");
  assert.equal(assignment.responses.checkout.answer, "At eleven");
});

test("Q&A tombstones remove deleted items without hiding newer recreations", () => {
  const storage = new MemoryStorage({
    [STORAGE_KEYS.qa]: scopeRoot(scopes.qa, {
      items: [
        { id: "qa:deleted", question: "old", createdAt: 100, updatedAt: 100 },
        { id: "qa:recreated", question: "new", createdAt: 300, updatedAt: 300 },
      ],
      updatedAt: 300,
    }),
  });

  mergeCheckpoint(storage, {
    qa: {
      items: [
        {
          id: "qa:deleted",
          question: "remote edit",
          createdAt: 100,
          updatedAt: 200,
        },
      ],
      tombstones: {
        "qa:deleted": 250,
        "qa:recreated": 200,
      },
      updatedAt: 250,
    },
  });

  const qa = storedRoot(storage, STORAGE_KEYS.qa).scopes[scopes.qa];
  assert.deepEqual(
    qa.items.map((item) => item.id),
    ["qa:recreated"],
  );
  assert.equal(qa.tombstones["qa:deleted"], 250);
  assert.equal(qa.tombstones["qa:recreated"], 200);
});

test("review schedule and favorite state merge independently", () => {
  const storage = new MemoryStorage({
    [STORAGE_KEYS.review]: scopeRoot(scopes.review, {
      cards: {
        book: {
          lastReviewedAt: 500,
          dueAt: 900,
          interval: 4,
          reviews: 2,
          lapses: 3,
          favorite: true,
          favoriteUpdatedAt: 100,
        },
      },
      updatedAt: 500,
    }),
  });

  mergeCheckpoint(storage, {
    review: {
      cards: {
        book: {
          lastReviewedAt: 400,
          dueAt: 600,
          interval: 2,
          reviews: 5,
          lapses: 1,
          favorite: false,
          favoriteUpdatedAt: 700,
        },
      },
      updatedAt: 700,
    },
  });

  const card =
    storedRoot(storage, STORAGE_KEYS.review).scopes[scopes.review].cards.book;
  assert.equal(card.lastReviewedAt, 500);
  assert.equal(card.dueAt, 900);
  assert.equal(card.interval, 4);
  assert.equal(card.favorite, false);
  assert.equal(card.favoriteUpdatedAt, 700);
  assert.equal(card.reviews, 5);
  assert.equal(card.lapses, 3);
});

test("review schedule recency includes card updates and homework queue time", () => {
  const storage = new MemoryStorage({
    [STORAGE_KEYS.review]: scopeRoot(scopes.review, {
      cards: {
        "updated-wins": {
          lastReviewedAt: 100,
          updatedAt: 900,
          dueAt: 1_900,
          interval: 9,
        },
        "queued-wins": {
          lastReviewedAt: 700,
          updatedAt: 700,
          dueAt: 1_700,
          interval: 7,
        },
      },
      updatedAt: 900,
    }),
  });

  mergeCheckpoint(storage, {
    review: {
      cards: {
        "updated-wins": {
          lastReviewedAt: 800,
          updatedAt: 800,
          dueAt: 1_800,
          interval: 8,
        },
        "queued-wins": {
          lastReviewedAt: 100,
          updatedAt: 100,
          homeworkQueuedAt: 850,
          dueAt: 1_850,
          interval: 85,
        },
      },
      updatedAt: 850,
    },
  });

  const cards =
    storedRoot(storage, STORAGE_KEYS.review).scopes[scopes.review].cards;
  assert.equal(
    cards["updated-wins"].dueAt,
    1_900,
    "a newer direct card update must beat an older review timestamp",
  );
  assert.equal(cards["updated-wins"].interval, 9);
  assert.equal(
    cards["queued-wins"].dueAt,
    1_850,
    "a newer homework queue mutation must win the review schedule",
  );
  assert.equal(cards["queued-wins"].homeworkQueuedAt, 850);
});

test("cloud bridge chunks event batches and keeps sync cursors out of bootstrap pagination", async () => {
  const events = Array.from({ length: 41 }, (_, index) => ({
    id: `le:${index + 1}`,
    occurredAt: 1_000 + index,
  }));
  const runtime = {
    adapter: new MemoryStorage(),
    transport: null,
    outbox: events.slice(),
    setTransport(transport) {
      this.transport = transport;
    },
    acknowledgeEvents(eventIds) {
      const acknowledged = new Set(eventIds);
      this.outbox = this.outbox.filter((event) => !acknowledged.has(event.id));
    },
    exportAll() {
      return {
        project: {
          scope: scopes.history,
        },
      };
    },
    async flush() {
      if (!this.outbox.length) return { status: "synced", pendingEvents: 0 };
      const result = await this.transport.pushBatch({
        schema: "fabulita.learning-batch.v1",
        scope: scopes.history,
        events: this.outbox,
        currentState: {
          rawScopes: {},
        },
      });
      const acknowledged = new Set(result.acknowledgedEventIds || []);
      this.outbox = this.outbox.filter((event) => !acknowledged.has(event.id));
      return { status: "synced", pendingEvents: this.outbox.length };
    },
  };
  const frame = {
    contentWindow: {
      fabulitaLearningPersistence: runtime,
      P: { config },
    },
    addEventListener() {
      throw new Error("unchanged bootstrap state must not reload the frame");
    },
  };
  const syncCalls = [];
  const bootstrapCalls = [];
  let checkpointVersion = 0;
  const bridge = createLearningCloudBridge({
    frame,
    async invoke(request) {
      if (request.action === "syncBatch") {
        syncCalls.push(request);
        checkpointVersion += 1;
        return {
          ok: true,
          acknowledgedEventIds: request.batch.events.map(
            (event) => event.id,
          ),
          checkpointVersion,
          cursor: "sync-cursor-must-not-be-used-for-bootstrap",
        };
      }
      if (request.action === "bootstrap") {
        bootstrapCalls.push(request);
        const firstPage = bootstrapCalls.length === 1;
        return {
          ok: true,
          checkpointVersion,
          checkpoint: { currentState: { rawScopes: {} } },
          events: [],
          cursor: firstPage
            ? "bootstrap-cursor-page-1"
            : "bootstrap-cursor-page-2",
          hasMore: firstPage,
        };
      }
      throw new Error(`unexpected action: ${request.action}`);
    },
  });

  await bridge.connect();

  assert.equal(syncCalls.length, 2);
  assert.equal(syncCalls[0].batch.events.length, 40);
  assert.equal(syncCalls[1].batch.events.length, 1);
  assert.deepEqual(syncCalls[0].batch.currentState, { rawScopes: {} });
  assert.deepEqual(
    syncCalls[1].batch.currentState,
    {},
    "only the first event chunk should carry the checkpoint state",
  );
  assert.deepEqual(
    syncCalls.flatMap((call) => call.batch.events.map((event) => event.id)),
    events.map((event) => event.id),
  );
  assert.equal(syncCalls[0].batch.baseCheckpointVersion, 0);
  assert.equal(syncCalls[1].batch.baseCheckpointVersion, 1);

  assert.equal(bootstrapCalls.length, 2);
  assert.equal(Object.hasOwn(bootstrapCalls[0], "cursor"), false);
  assert.equal(bootstrapCalls[1].cursor, "bootstrap-cursor-page-1");
  assert.notEqual(
    bootstrapCalls[1].cursor,
    "sync-cursor-must-not-be-used-for-bootstrap",
  );

  await bridge.flush();
  assert.equal(
    syncCalls.length,
    2,
    "an unchanged flush must not issue an empty syncBatch",
  );
  assert.equal(
    bootstrapCalls.length,
    3,
    "bootstrap polling may continue after the outbox is empty",
  );

  await bridge.disconnect();
  assert.equal(runtime.transport, null);
});

test("successful chunks are acknowledged before a later chunk fails", async () => {
  const events = Array.from({ length: 41 }, (_, index) => ({
    id: `le:partial:${index + 1}`,
    occurredAt: 2_000 + index,
  }));
  const runtime = {
    adapter: new MemoryStorage(),
    transport: null,
    outbox: events.slice(),
    setTransport(transport) {
      this.transport = transport;
    },
    acknowledgeEvents(eventIds) {
      const acknowledged = new Set(eventIds);
      this.outbox = this.outbox.filter((event) => !acknowledged.has(event.id));
    },
    exportAll() {
      return { project: { scope: scopes.history } };
    },
    async flush() {
      try {
        const result = await this.transport.pushBatch({
          schema: "fabulita.learning-batch.v1",
          scope: scopes.history,
          events: this.outbox,
          currentState: { rawScopes: { review: { updatedAt: 2_000 } } },
        });
        this.acknowledgeEvents(result.acknowledgedEventIds || []);
        return { status: "synced" };
      } catch (error) {
        return { status: "sync_failed", error: error.message };
      }
    },
  };
  const frame = {
    contentWindow: {
      fabulitaLearningPersistence: runtime,
      P: { config },
    },
  };
  let syncCalls = 0;
  const bridge = createLearningCloudBridge({
    frame,
    async invoke(request) {
      assert.equal(request.action, "syncBatch");
      syncCalls += 1;
      if (syncCalls === 2) throw new Error("second chunk failed");
      return {
        ok: true,
        checkpointVersion: 1,
        acknowledgedEventIds: request.batch.events.map((event) => event.id),
      };
    },
  });

  await assert.rejects(bridge.connect(), /second chunk failed/);
  assert.equal(syncCalls, 2);
  assert.deepEqual(
    runtime.outbox.map((event) => event.id),
    ["le:partial:41"],
    "the first 40 acknowledgements must survive the partial failure",
  );
});

test("bootstrap cursor survives bridge recreation and a first sync can read 100 pages", async () => {
  const adapter = new MemoryStorage();
  const runtime = {
    adapter,
    transport: null,
    setTransport(transport) {
      this.transport = transport;
    },
    exportAll() {
      return { project: { scope: scopes.history } };
    },
    async flush() {
      return { status: "synced", pendingEvents: 0 };
    },
  };
  const frame = {
    contentWindow: {
      fabulitaLearningPersistence: runtime,
      P: { config },
    },
  };
  let pages = 0;
  const firstBridge = createLearningCloudBridge({
    frame,
    async invoke(request) {
      assert.equal(request.action, "bootstrap");
      pages += 1;
      assert.equal(
        request.cursor,
        pages === 1 ? undefined : `page-${pages - 1}`,
      );
      return {
        ok: true,
        checkpointVersion: 0,
        checkpoint: { currentState: { rawScopes: {} } },
        events: [],
        cursor: `page-${pages}`,
        hasMore: pages < 100,
      };
    },
  });

  await firstBridge.connect();
  assert.equal(pages, 100);
  assert.equal(readBootstrapCursor(adapter, scopes.history), "page-100");
  await firstBridge.disconnect();

  let resumedRequest = null;
  const secondBridge = createLearningCloudBridge({
    frame,
    async invoke(request) {
      resumedRequest = request;
      return {
        ok: true,
        checkpointVersion: 0,
        checkpoint: { currentState: { rawScopes: {} } },
        events: [],
        cursor: "page-100",
        hasMore: false,
      };
    },
  });

  await secondBridge.connect();
  assert.equal(resumedRequest.cursor, "page-100");
});

test("an invalid persisted bootstrap cursor clears only its scope and retries once", async () => {
  const adapter = new MemoryStorage();
  const otherScope = "book:another-course:en";
  writeBootstrapCursor(adapter, scopes.history, "stale-after-restore");
  writeBootstrapCursor(adapter, otherScope, "keep-this-cursor");
  const runtime = {
    adapter,
    setTransport() {},
    exportAll() {
      return { project: { scope: scopes.history } };
    },
    async flush() {
      return { status: "synced", pendingEvents: 0 };
    },
  };
  const frame = {
    contentWindow: {
      fabulitaLearningPersistence: runtime,
      P: { config },
    },
  };
  const bootstrapCalls = [];
  const bridge = createLearningCloudBridge({
    frame,
    async invoke(request) {
      bootstrapCalls.push(request);
      if (bootstrapCalls.length === 1) {
        const error = new Error("cursor no longer exists");
        error.code = "INVALID_CURSOR";
        throw error;
      }
      return {
        ok: true,
        checkpointVersion: 0,
        checkpoint: { currentState: { rawScopes: {} } },
        events: [],
        cursor: "fresh-after-restore",
        hasMore: false,
      };
    },
  });

  await bridge.connect();

  assert.equal(bootstrapCalls.length, 2);
  assert.equal(bootstrapCalls[0].cursor, "stale-after-restore");
  assert.equal(
    Object.hasOwn(bootstrapCalls[1], "cursor"),
    false,
    "the one recovery request must restart from the beginning",
  );
  assert.equal(
    readBootstrapCursor(adapter, scopes.history),
    "fresh-after-restore",
  );
  assert.equal(
    readBootstrapCursor(adapter, otherScope),
    "keep-this-cursor",
    "restoring one course must not erase another course's cursor",
  );
});

test("a second invalid-cursor response fails without an infinite retry", async () => {
  const adapter = new MemoryStorage();
  const otherScope = "book:another-course:en";
  writeBootstrapCursor(adapter, scopes.history, "stale-after-restore");
  writeBootstrapCursor(adapter, otherScope, "keep-this-cursor");
  const runtime = {
    adapter,
    setTransport() {},
    exportAll() {
      return { project: { scope: scopes.history } };
    },
    async flush() {
      return { status: "synced", pendingEvents: 0 };
    },
  };
  const frame = {
    contentWindow: {
      fabulitaLearningPersistence: runtime,
      P: { config },
    },
  };
  let bootstrapCalls = 0;
  const bridge = createLearningCloudBridge({
    frame,
    async invoke(request) {
      bootstrapCalls += 1;
      if (bootstrapCalls === 1) {
        assert.equal(request.cursor, "stale-after-restore");
      } else {
        assert.equal(Object.hasOwn(request, "cursor"), false);
      }
      const error = new Error("database still rejects the cursor");
      error.code = "INVALID_CURSOR";
      throw error;
    },
  });

  await assert.rejects(bridge.connect(), /database still rejects the cursor/);
  assert.equal(bootstrapCalls, 2);
  assert.equal(readBootstrapCursor(adapter, scopes.history), "");
  assert.equal(readBootstrapCursor(adapter, otherScope), "keep-this-cursor");
});
