export class ApiError extends Error {
  constructor(message, { code = "REQUEST_FAILED", status = 0, cause } = {}) {
    super(message, { cause });
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

function parsePayload(text) {
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    return { message: text };
  }
}

function apiError(payload, status) {
  const nested = payload?.error;
  return new ApiError(
    payload?.message || nested?.message || "服务器暂时无法处理请求。",
    {
      code: payload?.code || nested?.code || `HTTP_${status || 0}`,
      status,
    },
  );
}

function normalizeUser(payload) {
  const user = payload?.user ?? payload?.data?.user ?? null;
  if (!user || typeof user !== "object") return null;
  const id = String(user.id || user.uid || user.sub || "").trim();
  const email = String(user.email || "").trim();
  if (!id) return null;
  return { ...user, id, email };
}

export function createApiClient({
  fetcher = globalThis.fetch?.bind(globalThis),
  baseUrl = "/api",
} = {}) {
  if (typeof fetcher !== "function") {
    throw new TypeError("当前浏览器不支持网络请求。");
  }

  let csrfToken = "";

  async function request(
    path,
    { method = "GET", body, requireCsrf = false } = {},
  ) {
    const headers = {
      Accept: "application/json",
    };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (requireCsrf && csrfToken) headers["X-CSRF-Token"] = csrfToken;

    let response;
    try {
      response = await fetcher(`${baseUrl}${path}`, {
        method,
        credentials: "include",
        headers,
        ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
      });
    } catch (error) {
      throw new ApiError("无法连接服务器，请检查网络后重试。", {
        code: "NETWORK_ERROR",
        cause: error,
      });
    }

    const payload = parsePayload(await response.text());
    if (!response.ok || payload?.ok === false) {
      throw apiError(payload, response.status);
    }
    return payload;
  }

  function rememberSession(payload) {
    csrfToken = String(
      payload?.csrfToken ?? payload?.data?.csrfToken ?? "",
    ).trim();
    return normalizeUser(payload);
  }

  return {
    async getCurrentUser() {
      const payload = await request("/auth/me");
      return rememberSession(payload);
    },

    async register({
      email,
      password,
      privacyConsent,
    }) {
      const payload = await request("/auth/register", {
        method: "POST",
        body: {
          email,
          password,
          privacyConsent,
        },
      });
      return rememberSession(payload);
    },

    async login({ email, password }) {
      const payload = await request("/auth/login", {
        method: "POST",
        body: { email, password },
      });
      return rememberSession(payload);
    },

    async logout() {
      try {
        return await request("/auth/logout", {
          method: "POST",
          body: {},
          requireCsrf: true,
        });
      } finally {
        csrfToken = "";
      }
    },

    action(actionRequest) {
      return request("/action", {
        method: "POST",
        body: actionRequest,
        requireCsrf: true,
      });
    },

    get csrfToken() {
      return csrfToken;
    },
  };
}
