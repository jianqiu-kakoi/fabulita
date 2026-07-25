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
  frame: null,
  guestLanding: document.querySelector("#guest-landing"),
  landingStatus: document.querySelector("#landing-status"),
  registerEntry: document.querySelector("#register-entry"),
  loginEntry: document.querySelector("#login-entry"),
  learningApp: document.querySelector("#learning-app"),
  learnerShell: document.querySelector("#learner-shell"),
  setupBanner: document.querySelector("#setup-banner"),
  syncState: document.querySelector("#sync-state"),
  syncStateText: document.querySelector("#sync-state span"),
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
  displayNameField: document.querySelector("#display-name-field"),
  displayNameInput: document.querySelector("#display-name-input"),
  emailInput: document.querySelector("#email-input"),
  passwordInput: document.querySelector("#password-input"),
  inviteCodeField: document.querySelector("#invite-code-field"),
  inviteCodeInput: document.querySelector("#invite-code-input"),
  privacyConsentRow: document.querySelector("#privacy-consent-row"),
  privacyConsent: document.querySelector("#privacy-consent"),
  formMessage: document.querySelector("#form-message"),
  authSubmitButton: document.querySelector("#auth-submit-button"),
  syncNowButton: document.querySelector("#sync-now-button"),
  logoutButton: document.querySelector("#logout-button"),
};

let currentUser = null;
let authMode = "login";
let registrationEnabled = false;
let sessionReady = false;
let activeLearningProfile = "";
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
    INVALID_DISPLAY_NAME: "请输入有效的姓名或称呼。",
    INVITE_INVALID_OR_USED: "邀请码不可用，请向邀请人确认后重试。",
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
  const target = String(profile || "");
  if (!currentUser || !target || target === "guest") {
    throw new Error("只有登录后才能加载学习页面。");
  }
  const runtime =
    elements.frame?.contentWindow?.fabulitaLearningPersistence || null;
  if (activeLearningProfile === target && runtime) return runtime;

  await bridge?.disconnect();
  bridge = null;
  elements.frame?.remove();
  elements.frame = null;

  const frame = document.createElement("iframe");
  frame.id = "learner-frame";
  frame.className = "learner-frame";
  frame.title = "My English 英语学习";
  const loaded = new Promise((resolve) => {
    frame.addEventListener("load", resolve, { once: true });
  });
  activeLearningProfile = target;
  frame.src = learnerUrl(target);
  elements.frame = frame;
  elements.learnerShell.replaceChildren(frame);
  bridge = createLearningCloudBridge({
    frame,
    invoke,
    onStatus: setSyncStatus,
  });
  await loaded;
  return frame.contentWindow?.fabulitaLearningPersistence || null;
}

async function destroyLearningExperience() {
  await bridge?.disconnect();
  bridge = null;
  activeLearningProfile = "";
  elements.frame?.remove();
  elements.frame = null;
  elements.learnerShell.replaceChildren();
}

async function activateUser(user) {
  if (!user) throw new Error("登录会话缺少用户信息。");
  // Reflect the authenticated server session before touching localStorage or
  // loading the learner. A local migration failure must never make a signed-in
  // shared device look signed out while its HttpOnly cookie is still valid.
  showAuthenticatedUi(user);
  const profile = profileForUser(user);
  claimGuestProgress(window.localStorage, profile);
  await switchLearningProfile(profile);
  await connectCloudProgress();
}

function showLearningLoadError(error) {
  if (currentUser) showAuthenticatedUi(currentUser);
  elements.setupBanner.hidden = false;
  elements.setupBanner.textContent =
    "账号已登录，但学习内容暂时没有加载成功，请刷新页面重试。";
  elements.setupBanner.title = error?.message || "";
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

function currentPrivacyConsent() {
  return {
    accepted: elements.privacyConsent.checked === true,
    version: PRIVACY_ACCEPTED_VERSION,
  };
}

function isValidDisplayName(value) {
  const normalized = String(value || "").trim();
  const length = [...normalized].length;
  return (
    length >= 1 &&
    length <= 80 &&
    !/[\u0000-\u001f\u007f]/.test(normalized)
  );
}

function updateRegistrationUi() {
  const registering = authMode === "register" && registrationEnabled;
  elements.displayNameField.hidden = !registering;
  elements.inviteCodeField.hidden = !registering;
  elements.privacyConsentRow.hidden = !registering;
  elements.displayNameInput.disabled = !registering;
  elements.inviteCodeInput.disabled = !registering;
  elements.privacyConsent.disabled = !registering;
  elements.displayNameInput.required = registering;
  elements.inviteCodeInput.required = registering;
  elements.privacyConsent.required = registering;
}

function setAuthMode(mode) {
  authMode =
    mode === "register" && registrationEnabled ? "register" : "login";
  const registering = authMode === "register";
  elements.loginModeButton.classList.toggle("is-active", !registering);
  elements.registerModeButton.classList.toggle("is-active", registering);
  elements.loginModeButton.setAttribute("aria-selected", String(!registering));
  elements.registerModeButton.setAttribute("aria-selected", String(registering));
  elements.dialogTitle.textContent = registering ? "创建学习账号" : "登录学习账号";
  elements.dialogCopy.textContent = registering
    ? "受邀测试用户可用一次性邀请码创建账号，并同步这台设备上的学习记录。"
    : "登录后进入学习页，并自动同步你的学习进度。";
  elements.passwordInput.autocomplete = registering
    ? "new-password"
    : "current-password";
  elements.authSubmitButton.textContent = registering
    ? "注册并同步进度"
    : "登录并同步进度";
  updateRegistrationUi();
  showMessage("");
}

function updateLandingEntries() {
  elements.loginEntry.disabled = !sessionReady;
  elements.registerEntry.disabled =
    !sessionReady || !registrationEnabled;
  elements.registerEntry.setAttribute(
    "aria-disabled",
    String(elements.registerEntry.disabled),
  );
}

function setRegistrationAvailability(health) {
  registrationEnabled =
    health?.registrationEnabled === true &&
    health?.privacyConsentVersion === PRIVACY_ACCEPTED_VERSION;
  elements.registerModeButton.hidden = !registrationEnabled;
  updateLandingEntries();
  elements.registerEntry.title = registrationEnabled
    ? ""
    : "邀请码注册暂时不可用";
  if (!registrationEnabled && authMode === "register") {
    setAuthMode("login");
  }
  updateRegistrationUi();
}

function showLoginPanel(mode = "login") {
  elements.loginPanel.hidden = false;
  elements.profilePanel.hidden = true;
  elements.accountForm.reset();
  elements.displayNameInput.removeAttribute("aria-invalid");
  elements.inviteCodeInput.removeAttribute("aria-invalid");
  setAuthMode(mode);
}

function showProfilePanel() {
  elements.loginPanel.hidden = true;
  elements.profilePanel.hidden = false;
  elements.profileCopy.textContent =
    `${maskEmail(currentUser?.email)} · 登录后自动同步学习进度`;
}

function openAccountDialog(mode = "login") {
  if (currentUser) showProfilePanel();
  else showLoginPanel(mode);
  elements.dialog.showModal();
  if (!currentUser) {
    const target =
      authMode === "register"
        ? elements.displayNameInput
        : elements.emailInput;
    setTimeout(() => target.focus(), 0);
  }
}

function showAuthenticatedUi(user) {
  elements.guestLanding.hidden = true;
  elements.learningApp.hidden = false;
  elements.accountLabel.textContent = maskEmail(user?.email);
  elements.setupBanner.hidden = true;
  document.body.classList.add("is-learning");
}

function showGuestUi() {
  elements.guestLanding.hidden = false;
  elements.learningApp.hidden = true;
  document.body.classList.remove("is-learning");
  setSyncStatus("local");
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
  if (currentUser) {
    await activateUser(currentUser);
  } else {
    await destroyLearningExperience();
    showGuestUi();
  }
  return currentUser;
}

function validateCredentials({
  requirePrivacy = false,
  requireInvitation = false,
} = {}) {
  const displayName = elements.displayNameInput.value.trim();
  if (
    requireInvitation &&
    (!isValidDisplayName(displayName) ||
      !elements.displayNameInput.checkValidity())
  ) {
    showMessage("请输入有效的姓名或称呼。", "error");
    elements.displayNameInput.setAttribute("aria-invalid", "true");
    elements.displayNameInput.focus();
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
  const inviteCode = elements.inviteCodeInput.value.trim();
  if (
    requireInvitation &&
    (!inviteCode || !elements.inviteCodeInput.checkValidity())
  ) {
    showMessage("请输入邀请人提供的一次性邀请码。", "error");
    elements.inviteCodeInput.setAttribute("aria-invalid", "true");
    elements.inviteCodeInput.focus();
    return null;
  }
  if (requirePrivacy && !elements.privacyConsent.checked) {
    showMessage("请先阅读并同意隐私说明。", "error");
    elements.privacyConsent.focus();
    return null;
  }
  if (requireInvitation) {
    return { displayName, email, password, inviteCode };
  }
  return { email, password };
}

async function authenticate() {
  const registering = authMode === "register";
  const credentials = validateCredentials({
    requirePrivacy: registering,
    requireInvitation: registering,
  });
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
          privacyConsent: currentPrivacyConsent(),
        })
      : await api.login(credentials);
    if (!currentUser) currentUser = await api.getCurrentUser();
    if (!currentUser) throw new Error("服务器没有返回登录账号。");
    showMessage("登录成功，正在合并本机与云端进度。", "success");
    try {
      await activateUser(currentUser);
    } catch (error) {
      showLearningLoadError(error);
    }
    elements.dialog.close();
  } catch (error) {
    currentUser = null;
    await destroyLearningExperience();
    showGuestUi();
    showMessage(friendlyError(error), "error");
    const code = String(error?.code || "").toUpperCase();
    if (registering && code === "INVITE_INVALID_OR_USED") {
      elements.inviteCodeInput.setAttribute("aria-invalid", "true");
      elements.inviteCodeInput.focus();
    } else if (registering && code === "INVALID_DISPLAY_NAME") {
      elements.displayNameInput.setAttribute("aria-invalid", "true");
      elements.displayNameInput.focus();
    }
  } finally {
    setBusy(elements.authSubmitButton, false);
  }
}

async function signOut() {
  setBusy(elements.logoutButton, true, "正在退出…");
  try {
    await api.logout();
    currentUser = null;
    await destroyLearningExperience();
    showGuestUi();
    elements.dialog.close();
  } catch (error) {
    elements.profileCopy.textContent = friendlyError(error);
  } finally {
    setBusy(elements.logoutButton, false);
  }
}

function initialize() {
  showGuestUi();
  api
    .getHealth()
    .then(setRegistrationAvailability)
    .catch(() => setRegistrationAvailability(null));

  refreshSession()
    .then(() => {
      sessionReady = true;
      updateLandingEntries();
    })
    .catch((error) => {
      if (currentUser) {
        showLearningLoadError(error);
        sessionReady = true;
        updateLandingEntries();
        return;
      }
      currentUser = null;
      sessionReady = false;
      updateLandingEntries();
      destroyLearningExperience().catch(() => {});
      showGuestUi();
      elements.landingStatus.hidden = false;
      elements.landingStatus.textContent =
        "账户服务暂时不可用，请稍后再试。";
      elements.landingStatus.title = error?.message || "";
    });
}

elements.registerEntry.addEventListener("click", () =>
  openAccountDialog("register"),
);
elements.loginEntry.addEventListener("click", () =>
  openAccountDialog("login"),
);
elements.accountButton.addEventListener("click", openAccountDialog);
elements.closeButton.addEventListener("click", () => elements.dialog.close());
elements.loginModeButton.addEventListener("click", () => setAuthMode("login"));
elements.registerModeButton.addEventListener("click", () =>
  setAuthMode("register"),
);
elements.displayNameInput.addEventListener("input", () => {
  elements.displayNameInput.removeAttribute("aria-invalid");
});
elements.inviteCodeInput.addEventListener("input", () => {
  elements.inviteCodeInput.removeAttribute("aria-invalid");
});
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
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden" && currentUser && bridge?.connected) {
    bridge.flush().catch(() => {});
  }
});
window.setInterval(() => {
  if (currentUser && bridge?.connected) bridge.flush().catch(() => {});
}, 30_000);

initialize();
