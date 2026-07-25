import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { ApiError, createApiClient } from "../src/api.js";

test("the no-JavaScript account form never sends credentials in a URL", () => {
  const html = readFileSync(
    new URL("../index.html", import.meta.url),
    "utf8",
  );
  assert.match(
    html,
    /<form\b[^>]*\bid="account-form"[^>]*\bmethod="dialog"/,
  );
});

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

test("health reports whether registration matches the active privacy notice", async () => {
  const calls = [];
  const api = createApiClient({
    async fetcher(url, options) {
      calls.push({ url, options });
      return jsonResponse({
        ok: true,
        registrationEnabled: false,
        emailVerificationEnabled: false,
        privacyConsentVersion: "2026-07-25",
      });
    },
  });

  assert.deepEqual(await api.getHealth(), {
    registrationEnabled: false,
    privacyConsentVersion: "2026-07-25",
  });
  assert.equal(calls[0].url, "/api/health");
  assert.equal(calls[0].options.method, "GET");
  assert.equal(api.csrfToken, "");
});

test("me uses the same-origin session cookie and remembers CSRF state", async () => {
  const calls = [];
  const api = createApiClient({
    async fetcher(url, options) {
      calls.push({ url, options });
      return jsonResponse({
        ok: true,
        user: { id: "user-1", email: "learner@example.com" },
        csrfToken: "csrf-from-me",
      });
    },
  });

  const user = await api.getCurrentUser();

  assert.deepEqual(user, {
    id: "user-1",
    email: "learner@example.com",
  });
  assert.equal(api.csrfToken, "csrf-from-me");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/auth/me");
  assert.equal(calls[0].options.method, "GET");
  assert.equal(calls[0].options.credentials, "include");
  assert.equal(calls[0].options.body, undefined);
});

test("signed-out me response becomes a guest without throwing", async () => {
  const api = createApiClient({
    fetcher: async () =>
      jsonResponse({ ok: true, user: null, csrfToken: null }),
  });

  assert.equal(await api.getCurrentUser(), null);
  assert.equal(api.csrfToken, "");
});

test("register sends invitation profile and privacy while login sends only credentials", async () => {
  const calls = [];
  const api = createApiClient({
    async fetcher(url, options) {
      calls.push({ url, options });
      return jsonResponse({
        ok: true,
        user: { id: `user-${calls.length}`, email: "a@example.com" },
        csrfToken: `csrf-${calls.length}`,
      });
    },
  });

  await api.register({
    displayName: "小秋",
    email: "a@example.com",
    password: "password-1",
    inviteCode: "ME-ABCDE-FGHIJ-KLMNO-PQRST-UVWXYZ",
    privacyConsent: {
      accepted: true,
      version: "2026-07-25",
    },
  });
  await api.login({ email: "a@example.com", password: "password-2" });

  assert.deepEqual(
    calls.map(({ url }) => url),
    ["/api/auth/register", "/api/auth/login"],
  );
  for (const call of calls) {
    assert.equal(call.options.method, "POST");
    assert.equal(call.options.credentials, "include");
    assert.equal(call.options.headers["Content-Type"], "application/json");
    assert.equal(call.options.headers["X-CSRF-Token"], undefined);
  }
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    displayName: "小秋",
    email: "a@example.com",
    password: "password-1",
    inviteCode: "ME-ABCDE-FGHIJ-KLMNO-PQRST-UVWXYZ",
    privacyConsent: {
      accepted: true,
      version: "2026-07-25",
    },
  });
  assert.deepEqual(JSON.parse(calls[1].options.body), {
    email: "a@example.com",
    password: "password-2",
  });
  assert.equal(api.csrfToken, "csrf-2");
});

test("login markup does not require registration consent", () => {
  const html = readFileSync(
    new URL("../index.html", import.meta.url),
    "utf8",
  );
  const consent = html.match(/<input\b[^>]*\bid="privacy-consent"[^>]*>/)?.[0];

  assert.ok(consent, "privacy consent checkbox should remain visible");
  assert.doesNotMatch(
    consent,
    /\brequired\b/,
    "the initial login mode must not be blocked by registration consent",
  );
});

test("registration stays hidden until the server explicitly enables it", () => {
  const html = readFileSync(
    new URL("../index.html", import.meta.url),
    "utf8",
  );
  const registerTab = html.match(
    /<button\b[^>]*\bid="auth-mode-register"[^>]*>/,
  )?.[0];

  assert.ok(registerTab, "registration tab should remain in the account UI");
  assert.match(registerTab, /\bhidden\b/);
});

test("name, invite, and consent controls are registration-only and form-safe", () => {
  const html = readFileSync(
    new URL("../index.html", import.meta.url),
    "utf8",
  );
  const nameField = html.match(
    /<label\b[^>]*\bid="display-name-field"[^>]*>/,
  )?.[0];
  const nameInput = html.match(
    /<input\b[^>]*\bid="display-name-input"[^>]*>/,
  )?.[0];
  const inviteField = html.match(
    /<label\b[^>]*\bid="invite-code-field"[^>]*>/,
  )?.[0];
  const inviteInput = html.match(
    /<input\b[^>]*\bid="invite-code-input"[^>]*>/,
  )?.[0];
  const consentRow = html.match(
    /<label\b[^>]*\bid="privacy-consent-row"[^>]*>/,
  )?.[0];

  assert.match(nameField, /\bhidden\b/);
  assert.match(nameInput, /\bname="displayName"/);
  assert.match(nameInput, /\bautocomplete="name"/);
  assert.match(nameInput, /\bdisabled\b/);
  assert.match(inviteField, /\bhidden\b/);
  assert.match(inviteInput, /\bname="inviteCode"/);
  assert.match(inviteInput, /ME-XXXXX-XXXXX-XXXXX-XXXXX-XXXXXX/);
  assert.match(inviteInput, /\bdisabled\b/);
  assert.match(consentRow, /\bhidden\b/);
  assert.doesNotMatch(html, /verification-code-input/);
  assert.doesNotMatch(html, /verification-send-button/);
});

test("invitation UI includes Chinese errors and no email-verification flow", () => {
  const mainSource = readFileSync(
    new URL("../src/main.js", import.meta.url),
    "utf8",
  );
  const apiSource = readFileSync(
    new URL("../src/api.js", import.meta.url),
    "utf8",
  );

  assert.match(mainSource, /INVITE_INVALID_OR_USED/);
  assert.match(mainSource, /INVALID_DISPLAY_NAME/);
  assert.match(mainSource, /requireInvitation:\s*registering/);
  assert.match(mainSource, /health\?\.registrationEnabled === true/);
  assert.doesNotMatch(mainSource, /emailVerificationEnabled/);
  assert.doesNotMatch(mainSource, /requestEmailVerification/);
  assert.doesNotMatch(apiSource, /auth\/verification\/request/);
});

test("privacy notice states that third-party model scoring is disabled", () => {
  const html = readFileSync(
    new URL("../privacy.html", import.meta.url),
    "utf8",
  );
  const scoringSection = html.match(
    /<h2>3\. 智能判分<\/h2>([\s\S]*?)<h2>4\./,
  )?.[1];

  assert.ok(scoringSection, "privacy notice should contain scoring section 3");
  assert.match(scoringSection, /当前智能判分和第三方模型服务尚未启用/);
  assert.match(scoringSection, /作答不会发送给第三方模型/);
  assert.match(scoringSection, /更新本说明/);
  assert.doesNotMatch(
    scoringSection,
    /class="todo"/,
    "the disabled provider section must not show a provider TODO",
  );
});

test("invite beta privacy notice discloses account fields and mail limits", () => {
  const privacy = readFileSync(
    new URL("../privacy.html", import.meta.url),
    "utf8",
  );

  assert.doesNotMatch(privacy, /正式上线前填写/);
  assert.match(privacy, /当前为邀请测试阶段/);
  assert.match(privacy, /Jianqiu Ye（叶剑秋）/);
  assert.match(privacy, /github\.com\/jianqiu-kakoi\/fabulita\/issues/);
  assert.match(privacy, /姓名或称呼、邮箱、密码及一次性邀请码/);
  assert.match(privacy, /当前不验证邮箱所有权/);
  assert.match(privacy, /邮件发送服务尚未启用/);
  assert.match(privacy, /不提供找回密码/);
  assert.match(privacy, /尚未提供自助导出或删除账号功能/);
});

test("action and logout attach the latest CSRF token", async () => {
  const calls = [];
  const api = createApiClient({
    async fetcher(url, options) {
      calls.push({ url, options });
      if (url.endsWith("/auth/me")) {
        return jsonResponse({
          ok: true,
          user: { id: "user-1", email: "a@example.com" },
          csrfToken: "csrf-current",
        });
      }
      return jsonResponse({ ok: true });
    },
  });

  await api.getCurrentUser();
  const actionResult = await api.action({
    action: "bootstrap",
    scope: "book:my-english:en",
  });
  await api.logout();

  assert.deepEqual(actionResult, { ok: true });
  assert.equal(calls[1].url, "/api/action");
  assert.equal(calls[1].options.credentials, "include");
  assert.equal(
    calls[1].options.headers["X-CSRF-Token"],
    "csrf-current",
  );
  assert.deepEqual(JSON.parse(calls[1].options.body), {
    action: "bootstrap",
    scope: "book:my-english:en",
  });
  assert.equal(calls[2].url, "/api/auth/logout");
  assert.equal(
    calls[2].options.headers["X-CSRF-Token"],
    "csrf-current",
  );
  assert.deepEqual(JSON.parse(calls[2].options.body), {});
  assert.equal(api.csrfToken, "");
});

test("API errors preserve status, code, and safe server message", async () => {
  const api = createApiClient({
    fetcher: async () =>
      jsonResponse(
        {
          ok: false,
          code: "INVALID_CREDENTIALS",
          message: "邮箱或密码不正确。",
        },
        401,
      ),
  });

  await assert.rejects(
    api.login({ email: "a@example.com", password: "wrong-pass" }),
    (error) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.status, 401);
      assert.equal(error.code, "INVALID_CREDENTIALS");
      assert.equal(error.message, "邮箱或密码不正确。");
      return true;
    },
  );
});

test("network failures become a stable frontend error", async () => {
  const api = createApiClient({
    fetcher: async () => {
      throw new TypeError("fetch failed");
    },
  });

  await assert.rejects(api.getCurrentUser(), {
    name: "ApiError",
    code: "NETWORK_ERROR",
  });
});
