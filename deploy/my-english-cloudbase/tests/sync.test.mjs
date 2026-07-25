import assert from "node:assert/strict";
import test from "node:test";

import {
  STORAGE_KEYS,
  claimGuestProgress,
  createLearningCloudBridge,
  learningScopes,
  mergeRemoteLearningState,
  profileStorageKey,
  userStorageProfile,
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
  });
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

test("cloud bridge chunks event batches and keeps sync cursors out of bootstrap pagination", async () => {
  const events = Array.from({ length: 41 }, (_, index) => ({
    id: `le:${index + 1}`,
    occurredAt: 1_000 + index,
  }));
  const runtime = {
    adapter: new MemoryStorage(),
    transport: null,
    setTransport(transport) {
      this.transport = transport;
    },
    exportAll() {
      return {
        project: {
          scope: scopes.history,
        },
      };
    },
    async flush() {
      await this.transport.pushBatch({
        schema: "fabulita.learning-batch.v1",
        scope: scopes.history,
        events,
        currentState: {
          rawScopes: {},
        },
      });
      return { status: "synced" };
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

  await bridge.disconnect();
  assert.equal(runtime.transport, null);
});
