import { createApiClient } from "./api.js";
import {
  claimGuestProgress,
  createLearningCloudBridge,
  userStorageProfile,
} from "./sync.js";
import "./styles.css";

const api = createApiClient();
const PRIVACY_ACCEPTED_VERSION = "2026-07-25";

const elements = {
  frame: document.querySelector("#learner-frame"),
  setupBanner: document.querySelector("#setup-banner"),
  syncState: document.querySelector("#sync-state"),
  syncStateText: document.querySelector("#sync-state span"),
  loginButton: document.querySelector("#login-button"),
  accountButton: document.querySelector("#account-button"),
  accountLabel: document.querySelector("#account-label"),
  dialog: document.querySelector("#account-dialog"),
  closeButton: document.querySelector(".dialog-close"),
  accountForm: document.querySelector("#account-form"),
  loginPanel: document.querySelector("#login-panel"),
  profilePanel: document.querySelector("#profile-panel"),
  profileCopy: document.querySelector("#profile-copy"),
  dialogTitle: document.querySelector("#dialog-title"),
  dialogCopy: document.querySelector("#dialog-copy"),
  loginModeButton: document.querySelector("#auth-mode-login"),
  registerModeButton: document.querySelector("#auth-mode-register"),
  emailInput: document.querySelector("#email-input"),
  passwordInput: document.querySelector("#password-input"),
  privacyConsent: document.querySelector("#privacy-consent"),
  formMessage: document.querySelector("#form-message"),
  authSubmitButton: document.querySelector("#auth-submit-button"),
  syncNowButton: document.querySelector("#sync-now-button"),
  logoutButton: document.querySelector("#logout-button"),
};

let currentUser = null;
let authMode = "login";
let activeLearningProfile = "guest";
let bridge = null;

function setSyncStatus(status, error) {
  const labels = {
    local: "本机保存",
    syncing: "正在同步",
    synced: "已同步",
    error: "同步稍后重试",
  };
  elements.syncState.className = `sync-state is-${status}`;
  elements.syncStateText.textContent = labels[status] || labels.local;
  elements.syncState.title = error?.message || "";
}

function friendlyError(error) {
  const code = String(error?.code || "").toUpperCase();
  const messages = {
    EMAIL_ALREADY_EXISTS: "这个邮箱已经注册，请直接登录。",
    EMAIL_ALREADY_REGISTERED: "这个邮箱已经注册，请直接登录。",
    INVALID_CREDENTIALS: "邮箱或密码不正确。",
    INVALID_EMAIL: "请输入正确的邮箱地址。",
    PASSWORD_TOO_SHORT: "密码至少需要 10 个字符。",
    WEAK_PASSWORD: "密码至少需要 10 个字符。",
    RATE_LIMITED: "操作太频繁，请稍后再试。",
    AUTH_RATE_LIMITED: "登录或注册尝试太频繁，请稍后再试。",
    TOO_MANY_REQUESTS: "操作太频繁，请稍后再试。",
    UNAUTHORIZED: "登录状态已失效，请重新登录。",
    MISSING_CREDENTIALS: "登录状态已失效，请重新登录。",
    AUTHENTICATION_REQUIRED: "登录状态已失效，请重新登录。",
    CSRF_INVALID: "登录状态已更新，请刷新页面后重试。",
    CSRF_TOKEN_INVALID: "登录状态已更新，请刷新页面后重试。",
    NETWORK_ERROR: "无法连接服务器，请检查网络后重试。",
    STORAGE_QUOTA_EXCEEDED: "云端学习数据已达到当前容量上限。",
    REGISTRATION_DISABLED: "当前暂未开放新账号注册，请稍后再试。",
    REGISTRATION_CLOSED: "当前暂未开放新账号注册，请稍后再试。",
    PRIVACY_CONSENT_REQUIRED: "请确认并同意当前版本的隐私说明后再注册。",
  };
  return messages[code] || error?.message || "暂时无法连接服务器，请稍后重试。";
}

function maskEmail(email) {
  const normalized = String(email || "").trim();
  const [name, domain] = normalized.split("@");
  if (!name || !domain) return "已登录";
  const visible = name.slice(0, Math.min(2, name.length));
  return `${visible}${name.length > 2 ? "•••" : ""}@${domain}`;
}

function profileForUser(user) {
  return user ? userStorageProfile(user.id) : "guest";
}

function learnerUrl(profile) {
  return `/my-english.html?storageProfile=${encodeURIComponent(profile)}`;
}

async function switchLearningProfile(profile) {
  const target = profile || "guest";
  const runtime =
    elements.frame.contentWindow?.fabulitaLearningPersistence || null;
  if (activeLearningProfile === target && runtime) return runtime;

  await bridge?.disconnect();
  const loaded = new Promise((resolve) => {
    elements.frame.addEventListener("load", resolve, { once: true });
  });
  activeLearningProfile = target;
  elements.frame.src = learnerUrl(target);
  await loaded;
  return elements.frame.contentWindow?.fabulitaLearningPersistence || null;
}

async function activateUser(user) {
  const profile = profileForUser(user);
  claimGuestProgress(window.localStorage, profile);
  await switchLearningProfile(profile);
  await connectCloudProgress();
}

function showMessage(message, kind = "") {
  elements.formMessage.textContent = message || "";
  elements.formMessage.dataset.kind = kind;
}

function setBusy(button, busy, label) {
  if (!button) return;
  if (busy) {
    button.dataset.label = button.textContent;
    button.textContent = label;
    button.disabled = true;
  } else {
    button.textContent = button.dataset.label || button.textContent;
    button.disabled = false;
    delete button.dataset.label;
  }
}

function setAuthMode(mode) {
  authMode = mode === "register" ? "register" : "login";
  const registering = authMode === "register";
  elements.loginModeButton.classList.toggle("is-active", !registering);
  elements.registerModeButton.classList.toggle("is-active", registering);
  elements.loginModeButton.setAttribute("aria-selected", String(!registering));
  elements.registerModeButton.setAttribute("aria-selected", String(registering));
  elements.dialogTitle.textContent = registering ? "创建学习账号" : "登录学习账号";
  elements.dialogCopy.textContent = registering
    ? "注册后会把这台设备上的学习记录合并到你的账号，并在设备间同步。"
    : "登录后自动合并本机与云端进度；未登录时仍可正常学习。";
  elements.passwordInput.autocomplete = registering
    ? "new-password"
    : "current-password";
  elements.authSubmitButton.textContent = registering
    ? "注册并同步进度"
    : "登录并同步进度";
  elements.privacyConsent.required = registering;
  showMessage("");
}

function showLoginPanel() {
  elements.loginPanel.hidden = false;
  elements.profilePanel.hidden = true;
  elements.accountForm.reset();
  setAuthMode("login");
}

function showProfilePanel() {
  elements.loginPanel.hidden = true;
  elements.profilePanel.hidden = false;
  elements.profileCopy.textContent =
    `${maskEmail(currentUser?.email)} · 登录后自动同步学习进度`;
}

function openAccountDialog() {
  if (currentUser) showProfilePanel();
  else showLoginPanel();
  elements.dialog.showModal();
  if (!currentUser) setTimeout(() => elements.emailInput.focus(), 0);
}

function updateAccountUi() {
  if (currentUser) {
    elements.loginButton.hidden = true;
    elements.accountButton.hidden = false;
    elements.accountLabel.textContent = maskEmail(currentUser.email);
  } else {
    elements.loginButton.hidden = false;
    elements.accountButton.hidden = true;
    setSyncStatus("local");
  }
}

async function invoke(data) {
  return api.action(data);
}

async function connectCloudProgress() {
  if (!currentUser || !bridge) return;
  try {
    await bridge.connect();
  } catch (error) {
    setSyncStatus("error", error);
  }
}

async function refreshSession() {
  currentUser = await api.getCurrentUser();
  updateAccountUi();
  if (currentUser) await activateUser(currentUser);
  else await switchLearningProfile("guest");
  return currentUser;
}

function validateCredentials({ requirePrivacy = false } = {}) {
  if (requirePrivacy && !elements.privacyConsent.checked) {
    showMessage("请先阅读并同意隐私说明。", "error");
    elements.privacyConsent.focus();
    return null;
  }
  if (!elements.emailInput.checkValidity()) {
    showMessage("请输入正确的邮箱地址。", "error");
    elements.emailInput.focus();
    return null;
  }
  const email = elements.emailInput.value.trim().toLowerCase();
  const password = elements.passwordInput.value;
  if (password.length < 10) {
    showMessage("密码至少需要 10 个字符。", "error");
    elements.passwordInput.focus();
    return null;
  }
  return { email, password };
}

async function authenticate() {
  const registering = authMode === "register";
  const credentials = validateCredentials({ requirePrivacy: registering });
  if (!credentials) return;
  setBusy(
    elements.authSubmitButton,
    true,
    registering ? "正在创建账号…" : "正在登录…",
  );
  showMessage("");
  try {
    currentUser = registering
      ? await api.register({
          ...credentials,
          privacyConsent: {
            accepted: elements.privacyConsent.checked === true,
            version: PRIVACY_ACCEPTED_VERSION,
          },
        })
      : await api.login(credentials);
    if (!currentUser) currentUser = await api.getCurrentUser();
    if (!currentUser) throw new Error("服务器没有返回登录账号。");
    elements.setupBanner.hidden = true;
    updateAccountUi();
    showMessage("登录成功，正在合并本机与云端进度。", "success");
    await activateUser(currentUser);
    elements.dialog.close();
  } catch (error) {
    currentUser = null;
    updateAccountUi();
    showMessage(friendlyError(error), "error");
  } finally {
    setBusy(elements.authSubmitButton, false);
  }
}

async function signOut() {
  setBusy(elements.logoutButton, true, "正在退出…");
  try {
    await api.logout();
    await bridge?.disconnect();
    currentUser = null;
    updateAccountUi();
    await switchLearningProfile("guest");
    elements.dialog.close();
  } catch (error) {
    elements.profileCopy.textContent = friendlyError(error);
  } finally {
    setBusy(elements.logoutButton, false);
  }
}

function initialize() {
  bridge = createLearningCloudBridge({
    frame: elements.frame,
    invoke,
    onStatus: setSyncStatus,
  });

  refreshSession().catch((error) => {
    currentUser = null;
    updateAccountUi();
    elements.setupBanner.hidden = false;
    elements.setupBanner.textContent =
      "账户服务暂时不可用，当前仍可正常学习，进度只保存在这台设备。";
    elements.setupBanner.title = error?.message || "";
  });
}

elements.loginButton.addEventListener("click", openAccountDialog);
elements.accountButton.addEventListener("click", openAccountDialog);
elements.closeButton.addEventListener("click", () => elements.dialog.close());
elements.loginModeButton.addEventListener("click", () => setAuthMode("login"));
elements.registerModeButton.addEventListener("click", () =>
  setAuthMode("register"),
);
elements.accountForm.addEventListener("submit", (event) => {
  event.preventDefault();
  authenticate();
});
elements.syncNowButton.addEventListener("click", async () => {
  setBusy(elements.syncNowButton, true, "正在同步…");
  try {
    await bridge.flush();
    elements.profileCopy.textContent = "刚刚完成同步，可以继续学习。";
  } catch (error) {
    elements.profileCopy.textContent = friendlyError(error);
  } finally {
    setBusy(elements.syncNowButton, false);
  }
});
elements.logoutButton.addEventListener("click", signOut);
elements.frame.addEventListener("load", () => {
  if (
    currentUser &&
    bridge &&
    activeLearningProfile === profileForUser(currentUser)
  ) {
    connectCloudProgress();
  }
});
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden" && currentUser && bridge?.connected) {
    bridge.flush().catch(() => {});
  }
});
window.setInterval(() => {
  if (currentUser && bridge?.connected) bridge.flush().catch(() => {});
}, 30_000);

initialize();
