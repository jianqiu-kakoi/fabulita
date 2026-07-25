import cloudbase from "@cloudbase/js-sdk";
import {
  claimGuestProgress,
  createLearningCloudBridge,
  unwrapFunctionResult,
  userStorageProfile,
} from "./sync.js";
import "./styles.css";

const config = {
  envId: String(import.meta.env.VITE_CLOUDBASE_ENV_ID || "").trim(),
  region: String(
    import.meta.env.VITE_CLOUDBASE_REGION || "ap-shanghai",
  ).trim(),
  functionName: String(
    import.meta.env.VITE_CLOUDBASE_FUNCTION_NAME || "my-english-api",
  ).trim(),
};

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
  loginForm: document.querySelector("#phone-login-form"),
  loginPanel: document.querySelector("#login-panel"),
  profilePanel: document.querySelector("#profile-panel"),
  profileCopy: document.querySelector("#profile-copy"),
  phoneInput: document.querySelector("#phone-input"),
  codeInput: document.querySelector("#code-input"),
  privacyConsent: document.querySelector("#privacy-consent"),
  verificationRow: document.querySelector("#verification-row"),
  formMessage: document.querySelector("#form-message"),
  sendCodeButton: document.querySelector("#send-code-button"),
  verifyCodeButton: document.querySelector("#verify-code-button"),
  syncNowButton: document.querySelector("#sync-now-button"),
  logoutButton: document.querySelector("#logout-button"),
};

let app = null;
let auth = null;
let currentSession = null;
let verifyOtp = null;
let cooldownTimer = null;
let bridge = null;
let activeLearningProfile = "guest";

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
  const code = String(error?.code || "").toLowerCase();
  if (code.includes("resource_exhausted")) return "发送太频繁，请稍后再试。";
  if (code.includes("invalid_argument")) return "请检查手机号或验证码。";
  if (code.includes("token") || code.includes("verification")) {
    return "验证码无效或已经过期，请重新获取。";
  }
  if (code.includes("unauthorized") || code.includes("missing_credentials")) {
    return "登录状态已失效，请重新登录。";
  }
  return error?.message || "暂时无法连接云端，请稍后重试。";
}

function normalizePhone(value) {
  const digits = String(value || "").replace(/\D/g, "");
  return /^1[3-9]\d{9}$/.test(digits) ? digits : "";
}

function maskPhone(phone) {
  const digits = String(phone || "").replace(/\D/g, "");
  if (digits.length < 7) return "已登录";
  return `${digits.slice(-11, -7)}****${digits.slice(-4)}`;
}

function sessionUser(session) {
  return session?.user || currentSession?.user || {};
}

function sessionUid(session) {
  const user = sessionUser(session);
  return String(user.id || user.uid || user.sub || user._id || "").trim();
}

function profileForSession(session) {
  return session ? userStorageProfile(sessionUid(session)) : "guest";
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

async function activateSession(session) {
  const profile = profileForSession(session);
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
  }
}

function showLoginPanel() {
  elements.loginPanel.hidden = false;
  elements.profilePanel.hidden = true;
  elements.verificationRow.hidden = true;
  elements.sendCodeButton.hidden = false;
  elements.verifyCodeButton.hidden = true;
  elements.codeInput.value = "";
  verifyOtp = null;
  showMessage("");
}

function showProfilePanel() {
  const user = sessionUser(currentSession);
  const phone = user.phone || user.phone_number || "";
  elements.loginPanel.hidden = true;
  elements.profilePanel.hidden = false;
  elements.profileCopy.textContent = `${maskPhone(phone)} · 登录后自动同步学习进度`;
}

function openAccountDialog() {
  if (currentSession) showProfilePanel();
  else showLoginPanel();
  elements.dialog.showModal();
  if (!currentSession) setTimeout(() => elements.phoneInput.focus(), 0);
}

function updateAccountUi() {
  if (currentSession) {
    const user = sessionUser(currentSession);
    elements.loginButton.hidden = true;
    elements.accountButton.hidden = false;
    elements.accountLabel.textContent = maskPhone(
      user.phone || user.phone_number || "",
    );
  } else {
    elements.loginButton.hidden = false;
    elements.accountButton.hidden = true;
    setSyncStatus("local");
  }
}

async function invoke(data) {
  if (!app) throw new Error("CloudBase 尚未配置。");
  const response = await app.callFunction({
    name: config.functionName,
    data,
    parse: true,
  });
  return unwrapFunctionResult(response);
}

async function connectCloudProgress() {
  if (!currentSession || !bridge) return;
  try {
    await bridge.connect();
  } catch (error) {
    setSyncStatus("error", error);
  }
}

async function refreshSession() {
  if (!auth) return null;
  const { data, error } = await auth.getSession();
  if (error) throw error;
  currentSession = data?.session || null;
  updateAccountUi();
  if (currentSession) await activateSession(currentSession);
  else await switchLearningProfile("guest");
  return currentSession;
}

function startCooldown(seconds = 30) {
  clearInterval(cooldownTimer);
  let remaining = seconds;
  elements.sendCodeButton.disabled = true;
  cooldownTimer = setInterval(() => {
    remaining -= 1;
    elements.sendCodeButton.textContent =
      remaining > 0 ? `${remaining} 秒后可重发` : "重新获取验证码";
    if (remaining <= 0) {
      clearInterval(cooldownTimer);
      cooldownTimer = null;
      elements.sendCodeButton.disabled = false;
    }
  }, 1000);
}

async function sendCode() {
  if (!elements.privacyConsent.checked) {
    showMessage("请先阅读并同意隐私说明。", "error");
    elements.privacyConsent.focus();
    return;
  }
  const phone = normalizePhone(elements.phoneInput.value);
  if (!phone) {
    showMessage("请输入正确的 11 位中国大陆手机号。", "error");
    elements.phoneInput.focus();
    return;
  }
  setBusy(elements.sendCodeButton, true, "正在发送…");
  showMessage("");
  try {
    const { data, error } = await auth.signInWithOtp({ phone });
    if (error) throw error;
    if (typeof data?.verifyOtp !== "function") {
      throw new Error("CloudBase 未返回验证码确认步骤。");
    }
    verifyOtp = data.verifyOtp;
    elements.verificationRow.hidden = false;
    elements.verifyCodeButton.hidden = false;
    showMessage("验证码已发送，有效期内输入即可登录。", "success");
    elements.codeInput.focus();
    startCooldown(30);
  } catch (error) {
    showMessage(friendlyError(error), "error");
  } finally {
    if (!cooldownTimer) setBusy(elements.sendCodeButton, false);
    else {
      elements.sendCodeButton.dataset.label = "重新获取验证码";
    }
  }
}

async function confirmCode() {
  const code = String(elements.codeInput.value || "").replace(/\D/g, "");
  if (!verifyOtp || code.length !== 6) {
    showMessage("请输入短信中的 6 位验证码。", "error");
    elements.codeInput.focus();
    return;
  }
  setBusy(elements.verifyCodeButton, true, "正在登录…");
  showMessage("");
  try {
    const { data, error } = await verifyOtp({ token: code });
    if (error) throw error;
    currentSession = data?.session || null;
    if (!currentSession) {
      await refreshSession();
    } else {
      updateAccountUi();
      await activateSession(currentSession);
    }
    showMessage("登录成功，正在合并本机与云端进度。", "success");
    elements.dialog.close();
  } catch (error) {
    showMessage(friendlyError(error), "error");
  } finally {
    setBusy(elements.verifyCodeButton, false);
  }
}

async function signOut() {
  setBusy(elements.logoutButton, true, "正在退出…");
  try {
    await bridge?.disconnect();
    await auth.signOut();
    currentSession = null;
    updateAccountUi();
    await switchLearningProfile("guest");
    elements.dialog.close();
  } catch (error) {
    elements.profileCopy.textContent = friendlyError(error);
  } finally {
    setBusy(elements.logoutButton, false);
  }
}

function initializeCloudBase() {
  if (!config.envId) {
    elements.setupBanner.hidden = false;
    elements.loginButton.disabled = true;
    elements.loginButton.title = "部署时填写 CloudBase 环境 ID 后启用";
    return;
  }

  app = cloudbase.init({
    env: config.envId,
    region: config.region,
    timeout: 60_000,
  });
  auth = app.auth;
  bridge = createLearningCloudBridge({
    frame: elements.frame,
    invoke,
    onStatus: setSyncStatus,
  });

  refreshSession().catch((error) => {
    currentSession = null;
    updateAccountUi();
    setSyncStatus("error", error);
  });
}

elements.loginButton.addEventListener("click", openAccountDialog);
elements.accountButton.addEventListener("click", openAccountDialog);
elements.closeButton.addEventListener("click", () => elements.dialog.close());
elements.loginForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (elements.verificationRow.hidden) sendCode();
  else confirmCode();
});
elements.verifyCodeButton.addEventListener("click", confirmCode);
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
    currentSession &&
    bridge &&
    activeLearningProfile === profileForSession(currentSession)
  ) {
    connectCloudProgress();
  }
});
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden" && currentSession && bridge?.connected) {
    bridge.flush().catch(() => {});
  }
});
window.setInterval(() => {
  if (currentSession && bridge?.connected) bridge.flush().catch(() => {});
}, 30_000);

initializeCloudBase();
