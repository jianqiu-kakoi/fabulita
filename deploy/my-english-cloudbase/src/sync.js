const STORAGE_KEYS = {
  review: "fabulita.review.v1",
  reviewEvents: "fabulita.review.events.v1",
  homework: "fabulita.homework.v1",
  homeworkStudy: "fabulita.homework.study.v1",
  qa: "fabulita.qa.v1",
  learningEvents: "fabulita.learning.events.v1",
};
const GUEST_CLAIM_KEY = "fabulita.cloudbase.guest.claimedBy";

export function userStorageProfile(uid) {
  const safe = String(uid || "")
    .trim()
    .replace(/[^A-Za-z0-9._-]/g, "_")
    .slice(0, 140);
  if (!safe) throw new Error("登录会话缺少用户标识。");
  return `user:${safe}`;
}

export function profileStorageKey(profile, key) {
  return profile && profile !== "guest"
    ? `fabulita.profile.${profile}.${key}`
    : key;
}

export function claimGuestProgress(storage, profile) {
  if (!storage || !profile || profile === "guest") return false;
  const claimedBy = storage.getItem(GUEST_CLAIM_KEY);
  if (claimedBy && claimedBy !== profile) return false;
  let changed = false;
  for (const key of Object.values(STORAGE_KEYS)) {
    const source = storage.getItem(key);
    const destination = profileStorageKey(profile, key);
    if (source != null && storage.getItem(destination) == null) {
      storage.setItem(destination, source);
      changed = true;
    }
  }
  storage.setItem(GUEST_CLAIM_KEY, profile);
  return changed;
}

function clone(value) {
  return value == null ? value : JSON.parse(JSON.stringify(value));
}

function isRecord(value) {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function timestamp(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? numeric : 0;
}

function parseJson(value, fallback) {
  try {
    const parsed = JSON.parse(value);
    return parsed == null ? fallback : parsed;
  } catch {
    return fallback;
  }
}

function storageRead(storage, key) {
  if (storage && typeof storage.getItem === "function") {
    return storage.getItem(key);
  }
  if (storage && typeof storage.read === "function") {
    return storage.read(key);
  }
  return null;
}

function storageWrite(storage, key, value) {
  if (storage && typeof storage.setItem === "function") {
    storage.setItem(key, value);
    return;
  }
  if (storage && typeof storage.write === "function") {
    storage.write(key, value);
    return;
  }
  throw new TypeError("学习存储适配器不可写。");
}

function normalizeProjectKey(value) {
  return String(value || "fabulita").normalize("NFC").toLowerCase();
}

export function learningScopes(config = {}) {
  const language = String(config.lang || "und");
  const historyProject = normalizeProjectKey(
    config.history_id || config.review_id || config.name,
  );
  const reviewProject = normalizeProjectKey(config.review_id || config.name);
  const homeworkProject = normalizeProjectKey(
    config.homework_id || config.history_id || config.review_id || config.name,
  );
  const qaProject = normalizeProjectKey(config.qa_id || config.name);

  return {
    history: `book:${historyProject}:${language}`,
    review: `book:${reviewProject}:${language}`,
    homework: `book:${homeworkProject}:${language}`,
    qa: `book:${qaProject}:${language}`,
  };
}

function eventTime(event) {
  return timestamp(event?.occurredAt || event?.reviewedAt || event?.updatedAt);
}

function mergeEventArrays(localEvents, remoteEvents) {
  const events = new Map();
  for (const raw of [...(localEvents || []), ...(remoteEvents || [])]) {
    if (!isRecord(raw) || typeof raw.id !== "string" || !raw.id) continue;
    const current = events.get(raw.id);
    if (!current || eventTime(raw) >= eventTime(current)) {
      events.set(raw.id, clone(raw));
    }
  }
  return [...events.values()].sort((a, b) => eventTime(b) - eventTime(a));
}

function mergeReviewScope(localScope, remoteScope) {
  if (!isRecord(localScope)) return clone(remoteScope);
  if (!isRecord(remoteScope)) return clone(localScope);

  const localCards = isRecord(localScope.cards) ? localScope.cards : {};
  const remoteCards = isRecord(remoteScope.cards) ? remoteScope.cards : {};
  const cards = {};
  const keys = new Set([...Object.keys(localCards), ...Object.keys(remoteCards)]);

  for (const key of keys) {
    const local = localCards[key];
    const remote = remoteCards[key];
    const localTime = timestamp(local?.lastReviewedAt || local?.homeworkQueuedAt);
    const remoteTime = timestamp(remote?.lastReviewedAt || remote?.homeworkQueuedAt);
    const schedule = clone(remoteTime > localTime ? remote : local ?? remote);
    const localFavoriteAt = timestamp(local?.favoriteUpdatedAt);
    const remoteFavoriteAt = timestamp(remote?.favoriteUpdatedAt);
    const favoriteSource =
      remoteFavoriteAt > localFavoriteAt ? remote : local ?? remote;
    if (isRecord(schedule) && isRecord(favoriteSource)) {
      if (typeof favoriteSource.favorite === "boolean") {
        schedule.favorite = favoriteSource.favorite;
      }
      if (favoriteSource.favoriteUpdatedAt) {
        schedule.favoriteUpdatedAt = favoriteSource.favoriteUpdatedAt;
      }
      schedule.reviews = Math.max(Number(local?.reviews || 0), Number(remote?.reviews || 0));
      schedule.lapses = Math.max(Number(local?.lapses || 0), Number(remote?.lapses || 0));
    }
    cards[key] = schedule;
  }

  const remoteIsNewer =
    timestamp(remoteScope.updatedAt) > timestamp(localScope.updatedAt);
  return {
    ...(remoteIsNewer ? clone(remoteScope) : clone(localScope)),
    cards,
    updatedAt: Math.max(
      timestamp(localScope.updatedAt),
      timestamp(remoteScope.updatedAt),
    ),
  };
}

function mergeAssignmentScope(localScope, remoteScope) {
  if (!isRecord(localScope)) return clone(remoteScope);
  if (!isRecord(remoteScope)) return clone(localScope);

  const localAssignments = isRecord(localScope.assignments)
    ? localScope.assignments
    : {};
  const remoteAssignments = isRecord(remoteScope.assignments)
    ? remoteScope.assignments
    : {};
  const assignments = {};
  const ids = new Set([
    ...Object.keys(localAssignments),
    ...Object.keys(remoteAssignments),
  ]);

  for (const id of ids) {
    const local = localAssignments[id];
    const remote = remoteAssignments[id];
    if (!isRecord(local)) {
      assignments[id] = clone(remote);
      continue;
    }
    if (!isRecord(remote)) {
      assignments[id] = clone(local);
      continue;
    }
    const remoteIsNewer =
      timestamp(remote.updatedAt) > timestamp(local.updatedAt);
    const merged = remoteIsNewer ? clone(remote) : clone(local);
    const localResponses = isRecord(local.responses) ? local.responses : {};
    const remoteResponses = isRecord(remote.responses) ? remote.responses : {};
    const responses = {};
    const responseIds = new Set([
      ...Object.keys(localResponses),
      ...Object.keys(remoteResponses),
    ]);
    const resetAt = Math.max(timestamp(local.resetAt), timestamp(remote.resetAt));
    for (const responseId of responseIds) {
      const localResponse = localResponses[responseId];
      const remoteResponse = remoteResponses[responseId];
      const selected =
        timestamp(remoteResponse?.updatedAt) > timestamp(localResponse?.updatedAt)
          ? remoteResponse
          : localResponse ?? remoteResponse;
      if (selected && timestamp(selected.updatedAt) >= resetAt) {
        responses[responseId] = clone(selected);
      }
    }
    merged.responses = responses;
    merged.updatedAt = Math.max(
      timestamp(local.updatedAt),
      timestamp(remote.updatedAt),
    );
    if (resetAt) merged.resetAt = resetAt;
    assignments[id] = merged;
  }

  const remoteIsNewer =
    timestamp(remoteScope.updatedAt) > timestamp(localScope.updatedAt);
  return {
    ...(remoteIsNewer ? clone(remoteScope) : clone(localScope)),
    assignments,
    updatedAt: Math.max(
      timestamp(localScope.updatedAt),
      timestamp(remoteScope.updatedAt),
    ),
  };
}

function mergeEventScope(localScope, remoteScope) {
  if (!isRecord(localScope)) return clone(remoteScope);
  if (!isRecord(remoteScope)) return clone(localScope);
  return {
    ...(timestamp(remoteScope.updatedAt) > timestamp(localScope.updatedAt)
      ? clone(remoteScope)
      : clone(localScope)),
    events: mergeEventArrays(localScope.events, remoteScope.events),
    updatedAt: Math.max(
      timestamp(localScope.updatedAt),
      timestamp(remoteScope.updatedAt),
    ),
  };
}

function newestScope(localScope, remoteScope) {
  if (!isRecord(localScope)) return clone(remoteScope);
  if (!isRecord(remoteScope)) return clone(localScope);
  return clone(
    timestamp(remoteScope.updatedAt) > timestamp(localScope.updatedAt)
      ? remoteScope
      : localScope,
  );
}

function mergeQaScope(localScope, remoteScope) {
  if (!isRecord(localScope)) return clone(remoteScope);
  if (!isRecord(remoteScope)) return clone(localScope);
  const items = new Map();
  for (const item of [...(localScope.items || []), ...(remoteScope.items || [])]) {
    if (!isRecord(item) || typeof item.id !== "string" || !item.id) continue;
    const current = items.get(item.id);
    const itemTime = timestamp(item.updatedAt || item.createdAt);
    const currentTime = timestamp(current?.updatedAt || current?.createdAt);
    if (!current || itemTime >= currentTime) items.set(item.id, clone(item));
  }
  const tombstones = {
    ...(isRecord(localScope.tombstones) ? localScope.tombstones : {}),
    ...(isRecord(remoteScope.tombstones) ? remoteScope.tombstones : {}),
  };
  for (const [id, deletedAt] of Object.entries(tombstones)) {
    const item = items.get(id);
    if (!item || timestamp(deletedAt) >= timestamp(item.updatedAt || item.createdAt)) {
      items.delete(id);
    }
  }
  const remoteIsNewer =
    timestamp(remoteScope.updatedAt) > timestamp(localScope.updatedAt);
  return {
    ...(remoteIsNewer ? clone(remoteScope) : clone(localScope)),
    items: [...items.values()].sort(
      (a, b) => timestamp(b.createdAt) - timestamp(a.createdAt),
    ),
    ...(Object.keys(tombstones).length ? { tombstones } : {}),
    updatedAt: Math.max(
      timestamp(localScope.updatedAt),
      timestamp(remoteScope.updatedAt),
    ),
  };
}

function mergeStoredScope(storage, key, scope, remoteScope, merge) {
  if (!isRecord(remoteScope)) return false;
  const root = parseJson(storageRead(storage, key), {
    version: 1,
    scopes: {},
  });
  const safeRoot =
    isRecord(root) && root.version === 1 && isRecord(root.scopes)
      ? root
      : { version: 1, scopes: {} };
  const localScope = safeRoot.scopes[scope];
  const mergedScope = merge(localScope, remoteScope);

  if (JSON.stringify(localScope ?? null) === JSON.stringify(mergedScope ?? null)) {
    return false;
  }
  safeRoot.scopes[scope] = mergedScope;
  storageWrite(storage, key, JSON.stringify(safeRoot));
  return true;
}

export function unwrapFunctionResult(response) {
  let result = response?.result ?? response;
  if (typeof result === "string") result = parseJson(result, result);
  if (isRecord(result) && typeof result.response_data === "string") {
    result = parseJson(result.response_data, result);
  }
  if (!isRecord(result)) {
    throw new Error("云函数返回了无法识别的数据。");
  }
  if (result.ok === false) {
    const error = new Error(result.message || "云端请求失败。");
    error.code = result.code || "CLOUD_REQUEST_FAILED";
    throw error;
  }
  return result;
}

export function mergeRemoteLearningState({
  storage,
  config,
  checkpoint,
  events = [],
}) {
  if (
    !storage ||
    (typeof storage.getItem !== "function" &&
      typeof storage.read !== "function")
  ) {
    return false;
  }
  const scopes = learningScopes(config);
  const state = checkpoint?.currentState;
  const rawScopes = isRecord(state?.rawScopes) ? state.rawScopes : {};
  let changed = false;

  changed =
    mergeStoredScope(
      storage,
      STORAGE_KEYS.review,
      scopes.review,
      rawScopes.review,
      mergeReviewScope,
    ) || changed;
  changed =
    mergeStoredScope(
      storage,
      STORAGE_KEYS.reviewEvents,
      scopes.history,
      rawScopes.reviewEvents,
      mergeEventScope,
    ) || changed;
  changed =
    mergeStoredScope(
      storage,
      STORAGE_KEYS.homework,
      scopes.homework,
      rawScopes.homework,
      mergeAssignmentScope,
    ) || changed;
  changed =
    mergeStoredScope(
      storage,
      STORAGE_KEYS.homeworkStudy,
      scopes.homework,
      rawScopes.homeworkStudy,
      mergeAssignmentScope,
    ) || changed;
  changed =
    mergeStoredScope(
      storage,
      STORAGE_KEYS.qa,
      scopes.qa,
      rawScopes.qa,
      mergeQaScope,
    ) || changed;

  if (Array.isArray(events) && events.length) {
    const remoteEventScope = {
      events,
      updatedAt: Math.max(...events.map(eventTime), 0),
    };
    changed =
      mergeStoredScope(
        storage,
        STORAGE_KEYS.learningEvents,
        scopes.history,
        remoteEventScope,
        mergeEventScope,
      ) || changed;
  }

  return changed;
}

function waitForFrameRuntime(frame, timeoutMs = 10_000) {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const inspect = () => {
      const runtime = frame.contentWindow?.fabulitaLearningPersistence;
      if (runtime) {
        resolve(runtime);
        return;
      }
      if (Date.now() - started >= timeoutMs) {
        reject(new Error("学习页面没有完成初始化。"));
        return;
      }
      setTimeout(inspect, 40);
    };
    inspect();
  });
}

function waitForNextLoad(frame) {
  return new Promise((resolve) => {
    frame.addEventListener("load", resolve, { once: true });
  });
}

export function createLearningCloudBridge({
  frame,
  invoke,
  onStatus = () => {},
}) {
  let connected = false;
  let connecting = null;
  let attachedRuntime = null;
  let checkpointVersion = 0;
  let cursor = null;
  let scope = "";

  async function attachRuntime(runtime) {
    if (runtime === attachedRuntime) return runtime;
    runtime.setTransport({
      async pushBatch(batch) {
        onStatus("syncing");
        try {
          const events = Array.isArray(batch.events) ? batch.events : [];
          const eventChunks = events.length
            ? Array.from(
                { length: Math.ceil(events.length / 40) },
                (_, index) => events.slice(index * 40, index * 40 + 40),
              )
            : [[]];
          let result = null;
          for (const eventChunk of eventChunks) {
            result = await invoke({
              action: "syncBatch",
              batch: {
                ...batch,
                events: eventChunk,
                baseCheckpointVersion: checkpointVersion,
              },
            });
            if (Number.isFinite(Number(result.checkpointVersion))) {
              checkpointVersion = Number(result.checkpointVersion);
            }
          }
          return result;
        } catch (error) {
          onStatus("error", error);
          throw error;
        }
      },
    });

    frame.contentWindow.fabulitaLearningServices = {
      async scoreAnswer(payload) {
        return invoke({ action: "scoreAnswer", payload });
      },
    };
    attachedRuntime = runtime;
    connected = true;
    return runtime;
  }

  async function pullRemote(runtime) {
    let changed = false;
    let page = 0;
    let previousCursor = null;
    do {
      const remote = await invoke({
        action: "bootstrap",
        scope,
        ...(cursor ? { cursor } : {}),
      });
      if (Number.isFinite(Number(remote.checkpointVersion))) {
        checkpointVersion = Number(remote.checkpointVersion);
      }
      changed =
        mergeRemoteLearningState({
          storage: runtime.adapter,
          config: frame.contentWindow.P?.config || {},
          checkpoint: remote.checkpoint,
          events: remote.events,
        }) || changed;
      previousCursor = cursor;
      if (remote.cursor) cursor = remote.cursor;
      page += 1;
      if (!remote.hasMore || !remote.cursor || remote.cursor === previousCursor) break;
    } while (page < 20);
    return changed;
  }

  async function syncCycle() {
    let runtime = await waitForFrameRuntime(frame);
    await attachRuntime(runtime);
    const local = runtime.exportAll();
    scope = local?.project?.scope;
    if (!scope) throw new Error("学习页面没有提供同步范围。");

    const report = await runtime.flush();
    if (report.status !== "synced") {
      throw new Error(report.error || "学习进度暂时无法同步。");
    }
    const changed = await pullRemote(runtime);
    if (changed) {
      const loaded = waitForNextLoad(frame);
      frame.contentWindow.location.reload();
      await loaded;
      runtime = await waitForFrameRuntime(frame);
      attachedRuntime = null;
      await attachRuntime(runtime);
      const followUp = await runtime.flush();
      if (followUp.status !== "synced") {
        throw new Error(followUp.error || "合并后的学习进度暂时无法同步。");
      }
    }
    onStatus("synced");
    return report;
  }

  async function connect() {
    if (connecting) return connecting;
    connecting = (async () => {
      onStatus("syncing");
      return syncCycle();
    })()
      .catch((error) => {
        onStatus("error", error);
        throw error;
      })
      .finally(() => {
        connecting = null;
      });
    return connecting;
  }

  async function flush() {
    return connect();
  }

  async function disconnect() {
    connected = false;
    checkpointVersion = 0;
    cursor = null;
    scope = "";
    const runtime = frame.contentWindow?.fabulitaLearningPersistence;
    if (runtime) runtime.setTransport(null);
    attachedRuntime = null;
    if (frame.contentWindow) {
      delete frame.contentWindow.fabulitaLearningServices;
    }
    onStatus("local");
  }

  return {
    connect,
    disconnect,
    flush,
    get connected() {
      return connected;
    },
  };
}

export { STORAGE_KEYS };
