import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const here = path.dirname(fileURLToPath(import.meta.url));
const learnerPath = path.resolve(here, "../../../../docs/my-english.html");

async function bootLearner() {
  const html = await readFile(learnerPath, "utf8");
  const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)]
    .map((match) => match[1]);
  const payloadMatch = scripts[0].match(/^var P = ([\s\S]*);$/);
  assert.ok(payloadMatch, "built learner payload should be readable");
  const P = JSON.parse(payloadMatch[1]);

  let application = scripts.at(-1);
  const close = application.lastIndexOf("})();");
  assert.notEqual(close, -1, "learner application should use its IIFE");
  application =
    application.slice(0, close) +
    `
      window.__outboxTest = {
        historyScopeKey,
        learningPersistence,
        learningEvents,
        learningEventsForExport,
        learningExportEnvelope,
        learningCurrentStateForSync
      };
    ` +
    application.slice(close);

  const storage = new Map();
  const localStorage = {
    getItem(key) {
      return storage.has(key) ? storage.get(key) : null;
    },
    setItem(key, value) {
      storage.set(key, String(value));
    },
    removeItem(key) {
      storage.delete(key);
    },
  };
  const noop = () => {};
  const classList = {
    add: noop,
    remove: noop,
    toggle: noop,
    contains: () => false,
  };
  const app = { className: "", innerHTML: "" };
  const pop = {
    classList,
    style: { setProperty: noop },
    offsetWidth: 0,
    offsetHeight: 0,
  };
  const document = {
    body: { classList, appendChild: noop },
    documentElement: { lang: "" },
    activeElement: null,
    title: "",
    addEventListener: noop,
    getElementById(id) {
      if (id === "app") return app;
      if (id === "pop") return pop;
      return null;
    },
    querySelector: () => null,
    querySelectorAll: () => [],
    createElement: () => ({ style: {}, click: noop, remove: noop }),
  };
  class AudioStub {
    pause() {}
    play() {
      return Promise.resolve();
    }
    addEventListener() {}
  }
  let uuid = 0;
  const context = {
    P,
    console,
    localStorage,
    document,
    location: { hash: "", search: "", reload: noop },
    navigator: {},
    setTimeout,
    clearTimeout,
    Intl,
    Date,
    Math,
    JSON,
    Blob: class BlobStub {},
    URL: { createObjectURL: () => "", revokeObjectURL: noop },
    crypto: {
      randomUUID() {
        uuid += 1;
        return `learner-outbox-${uuid}`;
      },
    },
    addEventListener: noop,
    scrollY: 0,
    scrollX: 0,
    innerWidth: 1200,
    innerHeight: 800,
    speechSynthesis: { cancel: noop, getVoices: () => [] },
    Audio: AudioStub,
  };
  context.window = context;
  vm.createContext(context);
  vm.runInContext(application, context);
  return { localStorage, runtime: context.__outboxTest };
}

function learningEvent(id, scope, occurredAt) {
  return {
    schema: "fabulita.learning-event.v1",
    id,
    occurredAt,
    scope,
    projectId: "my-english",
    language: "en",
    source: "qa",
    action: "question_created",
    entityId: id,
    sessionId: "test-session",
    prompt: `Question ${id}`,
    snapshotPersisted: true,
  };
}

function scopeRoot(scope, value) {
  return JSON.stringify({
    version: 1,
    scopes: { [scope]: value },
  });
}

test("learner migrates audit history once and only removes acknowledged outbox entries", async () => {
  const { localStorage, runtime } = await bootLearner();
  const scope = runtime.historyScopeKey;
  const existing = learningEvent("le:existing", scope, 1_000);
  localStorage.setItem(
    "fabulita.learning.events.v1",
    scopeRoot(scope, { events: [existing], updatedAt: 1_000 }),
  );
  localStorage.setItem(
    "fabulita.review.events.v1",
    scopeRoot(scope, {
      events: [{
        id: "legacy-review",
        type: "review_rated",
        reviewedAt: 900,
        sessionId: "legacy-session",
        historyScope: scope,
        wordKey: "w:book",
        word: "book",
        answerMode: "skipped",
        rating: "known",
      }],
      updatedAt: 900,
    }),
  );

  const batches = [];
  runtime.learningPersistence.setTransport({
    async pushBatch(batch) {
      batches.push(JSON.parse(JSON.stringify(batch)));
      return {
        ok: true,
        acknowledgedEventIds: batch.events.map((event) => event.id),
      };
    },
  });

  const first = await runtime.learningPersistence.flush();
  assert.equal(first.status, "synced");
  assert.deepEqual(
    batches[0].events.map((event) => event.id).sort(),
    ["le:existing", "legacy:legacy-review"],
  );
  assert.equal(
    Object.hasOwn(batches[0].currentState.rawScopes, "reviewEvents"),
    false,
    "append-only legacy review history must stay out of the cloud checkpoint",
  );

  const auditAfterAck = JSON.parse(
    localStorage.getItem("fabulita.learning.events.v1"),
  ).scopes[scope];
  const syncAfterAck = JSON.parse(
    localStorage.getItem("fabulita.learning.sync.v1"),
  ).scopes[scope];
  assert.deepEqual(
    auditAfterAck.events.map((event) => event.id),
    ["le:existing"],
    "acknowledgement must not delete immutable audit history",
  );
  assert.deepEqual(syncAfterAck.events, []);
  assert.deepEqual(
    syncAfterAck.acknowledgedEventIds,
    ["le:existing", "legacy:legacy-review"],
  );
  assert.equal(syncAfterAck.migrationVersion, 1);

  const second = await runtime.learningPersistence.flush();
  assert.equal(second.status, "synced");
  assert.equal(second.remote.skipped, true);
  assert.equal(
    batches.length,
    1,
    "an unchanged flush must not issue another syncBatch",
  );

  const appended = learningEvent("le:new", scope, 2_000);
  assert.equal(runtime.learningPersistence.appendEvent(appended), true);
  const queued = JSON.parse(
    localStorage.getItem("fabulita.learning.sync.v1"),
  ).scopes[scope];
  assert.deepEqual(
    queued.events.map((event) => event.id),
    ["le:new"],
    "new local events must enter the durable outbox",
  );

  await runtime.learningPersistence.flush();
  assert.equal(batches.length, 2);
  assert.deepEqual(
    batches[1].events.map((event) => event.id),
    ["le:new"],
  );
  const finalAudit = JSON.parse(
    localStorage.getItem("fabulita.learning.events.v1"),
  ).scopes[scope];
  assert.deepEqual(
    finalAudit.events.map((event) => event.id).sort(),
    ["le:existing", "le:new"],
  );
});
