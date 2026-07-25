import {
  createServer,
  type IncomingMessage,
  type Server,
  type ServerResponse,
} from "node:http";
import { timingSafeEqual } from "node:crypto";
import { isIP } from "node:net";
import type { SqliteDatabase } from "./database";
import { openDatabase } from "./database";
import {
  PRIVACY_CONSENT_VERSION,
  normalizeEmail,
  registrationVerificationEmail,
  SqliteAuthStore,
  type AuthenticatedSession,
  type PasswordWorkOptions,
} from "./auth";
import { SqliteAuthRateLimiter } from "./auth-rate-limit";
import {
  EMAIL_VERIFICATION_RESEND_SECONDS,
  EMAIL_VERIFICATION_TTL_SECONDS,
  NodemailerRegistrationVerificationEmailSender,
  type RegistrationVerificationEmailSender,
  type SmtpConfig,
} from "./email-verification";
import { ApiError, errorResponse } from "./errors";
import {
  OpenAiCompatibleAnswerScorer,
  type AnswerScorer,
} from "./llm";
import { createBackendService } from "./service";
import {
  DEFAULT_LEARNING_STORAGE_QUOTAS,
  SqliteLearningStore,
  type LearningStorageQuotas,
} from "./store";

const AUTH_BODY_LIMIT = 16 * 1024;
const ACTION_BODY_LIMIT = 1_100_000;
const LOGOUT_BODY_LIMIT = 1024;

export interface AppServerOptions {
  database: SqliteDatabase;
  allowedOrigins: ReadonlySet<string>;
  cookieName?: string;
  sessionTtlDays?: number;
  scoreLimitPerMinute?: number;
  scorer?: AnswerScorer;
  now?: () => number;
  authRateLimits?: Partial<AuthRateLimitConfig>;
  actionRequestsPerMinute?: number;
  learningQuotas?: Partial<LearningStorageQuotas>;
  llmGlobalLimits?: Partial<LlmGlobalLimitConfig>;
  registrationEnabled?: boolean;
  emailVerificationEnabled?: boolean;
  emailVerificationSecret?: string;
  verificationEmailSender?: RegistrationVerificationEmailSender;
  passwordWork?: PasswordWorkOptions;
}

export interface AuthRateLimitConfig {
  registerIpPerHour: number;
  registerEmailPerHour: number;
  verificationIpPerHour: number;
  verificationEmailPerHour: number;
  verificationGlobalPerMinute: number;
  verificationGlobalPerHour: number;
  verificationGlobalPerDay: number;
  loginIpPer15Minutes: number;
  loginEmailPer15Minutes: number;
}

export interface LlmGlobalLimitConfig {
  perMinute: number;
  perDay: number;
  concurrency: number;
}

export interface RuntimeConfig {
  host: string;
  port: number;
  databasePath: string;
  allowedOrigins: Set<string>;
  cookieName: string;
  sessionTtlDays: number;
  scoreLimitPerMinute: number;
  actionRequestsPerMinute: number;
  authRateLimits: AuthRateLimitConfig;
  learningQuotas: LearningStorageQuotas;
  llmGlobalLimits: LlmGlobalLimitConfig;
  registrationEnabled: boolean;
  emailVerificationEnabled: boolean;
  emailVerificationSecret: string;
  smtp: SmtpConfig | null;
  passwordWork: Required<PasswordWorkOptions>;
}

const DEFAULT_AUTH_RATE_LIMITS: AuthRateLimitConfig = {
  registerIpPerHour: 5,
  registerEmailPerHour: 3,
  verificationIpPerHour: 5,
  verificationEmailPerHour: 3,
  verificationGlobalPerMinute: 10,
  verificationGlobalPerHour: 100,
  verificationGlobalPerDay: 500,
  loginIpPer15Minutes: 30,
  loginEmailPer15Minutes: 10,
};

const DEFAULT_LLM_GLOBAL_LIMITS: LlmGlobalLimitConfig = {
  perMinute: 30,
  perDay: 500,
  concurrency: 4,
};

function boundedInteger(
  value: string | undefined,
  fallback: number,
  minimum: number,
  maximum: number,
): number {
  const parsed = Number(value);
  return Number.isFinite(parsed)
    ? Math.max(minimum, Math.min(maximum, Math.floor(parsed)))
    : fallback;
}

function booleanFlag(
  value: string | undefined,
  fallback: boolean,
  field: string,
): boolean {
  if (value == null || !value.trim()) return fallback;
  const normalized = value.trim().toLowerCase();
  if (normalized === "true") return true;
  if (normalized === "false") return false;
  throw new Error(`${field} must be true or false.`);
}

function normalizedOrigin(value: string): string {
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error(`Invalid origin in ALLOWED_ORIGINS: ${value}`);
  }
  const isLocal =
    parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1";
  if (parsed.protocol !== "https:" && !(isLocal && parsed.protocol === "http:")) {
    throw new Error(
      `ALLOWED_ORIGINS must use HTTPS except on localhost: ${value}`,
    );
  }
  if (
    parsed.username ||
    parsed.password ||
    parsed.pathname !== "/" ||
    parsed.search ||
    parsed.hash
  ) {
    throw new Error(
      `ALLOWED_ORIGINS entries must be bare origins: ${value}`,
    );
  }
  return parsed.origin;
}

function smtpConfig(
  environment: Record<string, string | undefined>,
  required: boolean,
): SmtpConfig | null {
  const keys = [
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_SECURE",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "SMTP_FROM",
  ] as const;
  const configured = keys.some((key) =>
    Boolean(environment[key]?.trim()),
  );
  if (!configured) return null;

  const missing = keys.filter((key) => {
    const value = environment[key];
    if (value == null || value.length === 0) return true;
    return key === "SMTP_PASSWORD" ? false : !value.trim();
  });
  if (missing.length > 0) {
    if (!required) return null;
    throw new Error(
      `SMTP configuration is incomplete: ${missing.join(", ")}.`,
    );
  }
  const rawPort = environment.SMTP_PORT!.trim();
  const port = Number(rawPort);
  if (
    !/^\d+$/.test(rawPort) ||
    !Number.isInteger(port) ||
    port < 1 ||
    port > 65_535
  ) {
    if (!required) return null;
    throw new Error("SMTP_PORT must be an integer from 1 to 65535.");
  }
  let secure: boolean;
  try {
    secure = booleanFlag(
      environment.SMTP_SECURE,
      false,
      "SMTP_SECURE",
    );
  } catch (error) {
    if (!required) return null;
    throw error;
  }
  return {
    host: environment.SMTP_HOST!.trim(),
    port,
    secure,
    user: environment.SMTP_USER!.trim(),
    password: environment.SMTP_PASSWORD!,
    from: environment.SMTP_FROM!.trim(),
    maxConcurrency: boundedInteger(
      environment.SMTP_MAX_CONCURRENCY,
      2,
      1,
      2,
    ),
  };
}

export function loadRuntimeConfig(
  environment: Record<string, string | undefined> = process.env,
): RuntimeConfig {
  const origins = (environment.ALLOWED_ORIGINS || "")
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean)
    .map(normalizedOrigin);
  if (origins.length === 0) {
    throw new Error("ALLOWED_ORIGINS is required.");
  }
  const cookieName =
    environment.COOKIE_NAME?.trim() || "__Host-my_english_session";
  if (!/^[A-Za-z0-9_-]{1,80}$/.test(cookieName)) {
    throw new Error("COOKIE_NAME contains unsupported characters.");
  }
  const databasePath = environment.DATABASE_PATH?.trim();
  if (!databasePath) throw new Error("DATABASE_PATH is required.");
  const registrationEnabled = booleanFlag(
    environment.REGISTRATION_ENABLED,
    false,
    "REGISTRATION_ENABLED",
  );
  const emailVerificationEnabled = booleanFlag(
    environment.EMAIL_VERIFICATION_ENABLED,
    false,
    "EMAIL_VERIFICATION_ENABLED",
  );
  const emailVerificationSecret =
    environment.EMAIL_VERIFICATION_SECRET?.trim() || "";
  const smtp = smtpConfig(environment, emailVerificationEnabled);
  if (
    registrationEnabled &&
    (
      !emailVerificationEnabled ||
      Buffer.byteLength(emailVerificationSecret, "utf8") < 32 ||
      !smtp
    )
  ) {
    throw new Error(
      "Open registration requires EMAIL_VERIFICATION_ENABLED=true, " +
        "EMAIL_VERIFICATION_SECRET with at least 32 bytes, and complete SMTP configuration.",
    );
  }
  if (
    emailVerificationEnabled &&
    (
      Buffer.byteLength(emailVerificationSecret, "utf8") < 32 ||
      !smtp
    )
  ) {
    throw new Error(
      "EMAIL_VERIFICATION_ENABLED=true requires EMAIL_VERIFICATION_SECRET " +
        "with at least 32 bytes and complete SMTP configuration.",
    );
  }
  return {
    host: environment.HOST?.trim() || "127.0.0.1",
    port: boundedInteger(environment.PORT, 3000, 1, 65_535),
    databasePath,
    allowedOrigins: new Set(origins),
    cookieName,
    registrationEnabled,
    emailVerificationEnabled,
    emailVerificationSecret,
    smtp,
    sessionTtlDays: boundedInteger(
      environment.SESSION_TTL_DAYS,
      30,
      1,
      90,
    ),
    scoreLimitPerMinute: boundedInteger(
      environment.LLM_RATE_LIMIT_PER_MINUTE,
      10,
      1,
      60,
    ),
    actionRequestsPerMinute: boundedInteger(
      environment.ACTION_RATE_LIMIT_PER_MINUTE,
      240,
      10,
      1000,
    ),
    authRateLimits: {
      registerIpPerHour: boundedInteger(
        environment.AUTH_REGISTER_IP_LIMIT_PER_HOUR,
        DEFAULT_AUTH_RATE_LIMITS.registerIpPerHour,
        1,
        1000,
      ),
      registerEmailPerHour: boundedInteger(
        environment.AUTH_REGISTER_EMAIL_LIMIT_PER_HOUR,
        DEFAULT_AUTH_RATE_LIMITS.registerEmailPerHour,
        1,
        1000,
      ),
      verificationIpPerHour: boundedInteger(
        environment.AUTH_VERIFICATION_IP_LIMIT_PER_HOUR,
        DEFAULT_AUTH_RATE_LIMITS.verificationIpPerHour,
        1,
        1000,
      ),
      verificationEmailPerHour: boundedInteger(
        environment.AUTH_VERIFICATION_EMAIL_LIMIT_PER_HOUR,
        DEFAULT_AUTH_RATE_LIMITS.verificationEmailPerHour,
        1,
        1000,
      ),
      verificationGlobalPerMinute: boundedInteger(
        environment.AUTH_VERIFICATION_GLOBAL_LIMIT_PER_MINUTE,
        DEFAULT_AUTH_RATE_LIMITS.verificationGlobalPerMinute,
        1,
        10_000,
      ),
      verificationGlobalPerHour: boundedInteger(
        environment.AUTH_VERIFICATION_GLOBAL_LIMIT_PER_HOUR,
        DEFAULT_AUTH_RATE_LIMITS.verificationGlobalPerHour,
        1,
        100_000,
      ),
      verificationGlobalPerDay: boundedInteger(
        environment.AUTH_VERIFICATION_GLOBAL_LIMIT_PER_DAY,
        DEFAULT_AUTH_RATE_LIMITS.verificationGlobalPerDay,
        1,
        1_000_000,
      ),
      loginIpPer15Minutes: boundedInteger(
        environment.AUTH_LOGIN_IP_LIMIT_PER_15_MINUTES,
        DEFAULT_AUTH_RATE_LIMITS.loginIpPer15Minutes,
        1,
        1000,
      ),
      loginEmailPer15Minutes: boundedInteger(
        environment.AUTH_LOGIN_EMAIL_LIMIT_PER_15_MINUTES,
        DEFAULT_AUTH_RATE_LIMITS.loginEmailPer15Minutes,
        1,
        1000,
      ),
    },
    learningQuotas: {
      maxEventsPerUser: boundedInteger(
        environment.MAX_EVENTS_PER_USER,
        DEFAULT_LEARNING_STORAGE_QUOTAS.maxEventsPerUser,
        100,
        1_000_000,
      ),
      maxEventBytesPerUser: boundedInteger(
        environment.MAX_EVENT_BYTES_PER_USER,
        DEFAULT_LEARNING_STORAGE_QUOTAS.maxEventBytesPerUser,
        1024 * 1024,
        1024 * 1024 * 1024,
      ),
      maxScopesPerUser: boundedInteger(
        environment.MAX_SCOPES_PER_USER,
        DEFAULT_LEARNING_STORAGE_QUOTAS.maxScopesPerUser,
        1,
        1000,
      ),
      maxCheckpointBytesPerUser: boundedInteger(
        environment.MAX_CHECKPOINT_BYTES_PER_USER,
        DEFAULT_LEARNING_STORAGE_QUOTAS.maxCheckpointBytesPerUser,
        1024 * 1024,
        256 * 1024 * 1024,
      ),
    },
    llmGlobalLimits: {
      perMinute: boundedInteger(
        environment.LLM_GLOBAL_RATE_LIMIT_PER_MINUTE,
        DEFAULT_LLM_GLOBAL_LIMITS.perMinute,
        1,
        10_000,
      ),
      perDay: boundedInteger(
        environment.LLM_GLOBAL_RATE_LIMIT_PER_DAY,
        DEFAULT_LLM_GLOBAL_LIMITS.perDay,
        1,
        1_000_000,
      ),
      concurrency: boundedInteger(
        environment.LLM_MAX_CONCURRENCY,
        DEFAULT_LLM_GLOBAL_LIMITS.concurrency,
        1,
        100,
      ),
    },
    passwordWork: {
      concurrency: boundedInteger(
        environment.PASSWORD_SCRYPT_CONCURRENCY,
        2,
        1,
        2,
      ),
      queueLimit: boundedInteger(
        environment.PASSWORD_SCRYPT_QUEUE_LIMIT,
        8,
        0,
        64,
      ),
    },
  };
}

function requestOrigin(request: IncomingMessage): string {
  const value = request.headers.origin;
  return typeof value === "string" ? value : "";
}

function assertAllowedOrigin(
  request: IncomingMessage,
  allowedOrigins: ReadonlySet<string>,
): string {
  const rawOrigin = requestOrigin(request);
  if (!rawOrigin) {
    throw new ApiError(
      "CSRF_ORIGIN_REQUIRED",
      "A trusted Origin header is required.",
      403,
    );
  }
  let origin = "";
  try {
    origin = new URL(rawOrigin).origin;
  } catch {
    // Rejected below.
  }
  if (!origin || rawOrigin !== origin || !allowedOrigins.has(origin)) {
    throw new ApiError(
      "ORIGIN_NOT_ALLOWED",
      "This request origin is not allowed.",
      403,
    );
  }
  const fetchSite = request.headers["sec-fetch-site"];
  if (
    typeof fetchSite === "string" &&
    fetchSite !== "same-origin" &&
    fetchSite !== "same-site" &&
    fetchSite !== "none"
  ) {
    throw new ApiError(
      "ORIGIN_NOT_ALLOWED",
      "Cross-site browser requests are not allowed.",
      403,
    );
  }
  return origin;
}

function applyBaseHeaders(
  response: ServerResponse,
  request: IncomingMessage,
  allowedOrigins: ReadonlySet<string>,
): void {
  response.setHeader("Cache-Control", "no-store");
  response.setHeader("X-Content-Type-Options", "nosniff");
  response.setHeader("Referrer-Policy", "same-origin");
  response.setHeader("Permissions-Policy", "camera=(), microphone=(), geolocation=()");
  const origin = requestOrigin(request);
  if (origin && allowedOrigins.has(origin)) {
    response.setHeader("Access-Control-Allow-Origin", origin);
    response.setHeader("Access-Control-Allow-Credentials", "true");
    response.setHeader("Vary", "Origin");
  }
}

function sendJson(
  response: ServerResponse,
  status: number,
  value: unknown,
): void {
  const body = JSON.stringify(value);
  response.statusCode = status;
  response.setHeader("Content-Type", "application/json; charset=utf-8");
  response.setHeader("Content-Length", Buffer.byteLength(body));
  response.end(body);
}

async function readJson(
  request: IncomingMessage,
  limit: number,
  allowEmpty = false,
): Promise<unknown> {
  const type = request.headers["content-type"];
  if (
    typeof type !== "string" ||
    !/^application\/json(?:\s*;|$)/i.test(type)
  ) {
    throw new ApiError(
      "UNSUPPORTED_MEDIA_TYPE",
      "Content-Type must be application/json.",
      415,
    );
  }
  const declaredLength = Number(request.headers["content-length"]);
  if (
    Number.isFinite(declaredLength) &&
    declaredLength > limit
  ) {
    request.resume();
    throw new ApiError(
      "PAYLOAD_TOO_LARGE",
      `JSON request body exceeds the ${limit}-byte limit.`,
      413,
    );
  }

  const chunks: Uint8Array[] = [];
  let size = 0;
  let exceeded = false;
  for await (const chunk of request) {
    const bytes =
      typeof chunk === "string" ? Buffer.from(chunk) : chunk;
    size += bytes.byteLength;
    if (size > limit) {
      exceeded = true;
      continue;
    }
    chunks.push(bytes);
  }
  if (exceeded) {
    throw new ApiError(
      "PAYLOAD_TOO_LARGE",
      `JSON request body exceeds the ${limit}-byte limit.`,
      413,
    );
  }
  const text = Buffer.concat(chunks).toString("utf8");
  if (!text.trim()) {
    if (allowEmpty) return {};
    throw new ApiError("INVALID_JSON", "JSON request body is required.");
  }
  try {
    return JSON.parse(text) as unknown;
  } catch {
    throw new ApiError("INVALID_JSON", "Request body is not valid JSON.");
  }
}

function parseCookies(request: IncomingMessage): Map<string, string> {
  const cookies = new Map<string, string>();
  const raw = request.headers.cookie;
  if (!raw) return cookies;
  for (const part of raw.split(";")) {
    const separator = part.indexOf("=");
    if (separator < 1) continue;
    const name = part.slice(0, separator).trim();
    const value = part.slice(separator + 1).trim();
    try {
      cookies.set(name, decodeURIComponent(value));
    } catch {
      // Ignore malformed cookies.
    }
  }
  return cookies;
}

function sessionCookie(
  cookieName: string,
  token: string,
  maxAgeSeconds: number,
): string {
  return [
    `${cookieName}=${encodeURIComponent(token)}`,
    "Path=/",
    "HttpOnly",
    "Secure",
    "SameSite=Lax",
    `Max-Age=${Math.max(0, Math.floor(maxAgeSeconds))}`,
  ].join("; ");
}

function clearSessionCookie(cookieName: string): string {
  return [
    `${cookieName}=`,
    "Path=/",
    "HttpOnly",
    "Secure",
    "SameSite=Lax",
    "Max-Age=0",
    "Expires=Thu, 01 Jan 1970 00:00:00 GMT",
  ].join("; ");
}

function constantTimeTextEqual(left: string, right: string): boolean {
  const leftBytes = Buffer.from(left);
  const rightBytes = Buffer.from(right);
  return (
    leftBytes.length === rightBytes.length &&
    timingSafeEqual(leftBytes, rightBytes)
  );
}

function requireSession(
  request: IncomingMessage,
  store: SqliteAuthStore,
  cookieName: string,
  now: number,
): {
  rawToken: string;
  session: AuthenticatedSession;
} {
  const rawToken = parseCookies(request).get(cookieName) || "";
  const session = store.getSession(rawToken, now);
  if (!session) {
    throw new ApiError(
      "AUTHENTICATION_REQUIRED",
      "Sign in before using this endpoint.",
      401,
    );
  }
  return { rawToken, session };
}

function assertCsrf(
  request: IncomingMessage,
  session: AuthenticatedSession,
): void {
  const header = request.headers["x-csrf-token"];
  if (
    typeof header !== "string" ||
    !header ||
    !constantTimeTextEqual(header, session.csrfToken)
  ) {
    throw new ApiError(
      "CSRF_TOKEN_INVALID",
      "The CSRF token is missing or invalid.",
      403,
    );
  }
}

function pathFor(request: IncomingMessage): string {
  try {
    return new URL(request.url || "/", "http://internal.invalid").pathname;
  } catch {
    return "/";
  }
}

function authEmail(value: unknown): string {
  if (value == null || typeof value !== "object" || Array.isArray(value)) {
    throw new ApiError("INVALID_INPUT", "request must be an object.");
  }
  return normalizeEmail((value as Record<string, unknown>).email);
}

function clientAddress(request: IncomingMessage): string {
  const direct = request.socket.remoteAddress || "unknown";
  const loopback =
    direct === "127.0.0.1" ||
    direct === "::1" ||
    direct === "::ffff:127.0.0.1";
  const forwarded = request.headers["x-forwarded-for"];
  if (loopback && typeof forwarded === "string" && forwarded.length <= 500) {
    const first = forwarded.split(",", 1)[0].trim();
    if (isIP(first)) return first;
  }
  return direct.startsWith("::ffff:") ? direct.slice(7) : direct;
}

function globallyLimitedScorer(
  scorer: AnswerScorer,
  limiter: SqliteAuthRateLimiter,
  limits: LlmGlobalLimitConfig,
  now: () => number,
): AnswerScorer {
  let active = 0;
  return {
    async score(input, rubric) {
      if (active >= limits.concurrency) {
        throw new ApiError(
          "SCORING_CAPACITY_REACHED",
          "The scoring service is busy. Please try again shortly.",
          429,
          1000,
        );
      }
      const budget = limiter.consume(
        [
          {
            bucket: "llm:global:minute",
            subject: "server",
            limit: limits.perMinute,
            windowMs: 60_000,
          },
          {
            bucket: "llm:global:day",
            subject: "server",
            limit: limits.perDay,
            windowMs: 24 * 60 * 60_000,
          },
        ],
        now(),
      );
      if (!budget.allowed) {
        throw new ApiError(
          "SCORING_CAPACITY_REACHED",
          "The scoring budget is temporarily exhausted.",
          429,
          budget.retryAfterMs,
        );
      }
      active += 1;
      try {
        return await scorer.score(input, rubric);
      } finally {
        active -= 1;
      }
    },
  };
}

export function createAppServer(options: AppServerOptions): Server {
  const now = options.now || Date.now;
  const cookieName =
    options.cookieName || "__Host-my_english_session";
  const authStore = new SqliteAuthStore(
    options.database,
    options.sessionTtlDays || 30,
    options.passwordWork,
    { secret: options.emailVerificationSecret },
  );
  const authLimiter = new SqliteAuthRateLimiter(options.database);
  const authLimits: AuthRateLimitConfig = {
    ...DEFAULT_AUTH_RATE_LIMITS,
    ...options.authRateLimits,
  };
  const learningStore = new SqliteLearningStore(
    options.database,
    options.learningQuotas,
  );
  const scorer = globallyLimitedScorer(
    options.scorer || OpenAiCompatibleAnswerScorer.fromEnvironment(),
    authLimiter,
    {
      ...DEFAULT_LLM_GLOBAL_LIMITS,
      ...options.llmGlobalLimits,
    },
    now,
  );

  const server = createServer(async (request, response) => {
    applyBaseHeaders(response, request, options.allowedOrigins);
    const path = pathFor(request);
    try {
      if (request.method === "OPTIONS" && path.startsWith("/api/")) {
        assertAllowedOrigin(request, options.allowedOrigins);
        response.statusCode = 204;
        response.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
        response.setHeader(
          "Access-Control-Allow-Headers",
          "Content-Type, X-CSRF-Token",
        );
        response.setHeader("Access-Control-Max-Age", "600");
        response.end();
        return;
      }

      if (request.method === "GET" && path === "/api/health") {
        options.database.prepare("SELECT 1 AS ok").get();
        sendJson(response, 200, {
          ok: true,
          service: "my-english-api",
          version: "0.2.0",
          registrationEnabled: options.registrationEnabled === true,
          emailVerificationEnabled:
            options.emailVerificationEnabled === true,
          privacyConsentVersion: PRIVACY_CONSENT_VERSION,
          serverTime: new Date(now()).toISOString(),
        });
        return;
      }

      if (request.method === "GET" && path === "/api/auth/me") {
        const rawToken = parseCookies(request).get(cookieName) || "";
        const session = authStore.getSession(rawToken, now());
        sendJson(response, 200, {
          ok: true,
          user: session?.user || null,
          csrfToken: session?.csrfToken || null,
        });
        return;
      }

      if (
        request.method === "POST" &&
        path === "/api/auth/verification/request"
      ) {
        assertAllowedOrigin(request, options.allowedOrigins);
        if (
          options.registrationEnabled !== true ||
          options.emailVerificationEnabled !== true
        ) {
          throw new ApiError(
            "REGISTRATION_CLOSED",
            "New account registration is currently closed.",
            403,
          );
        }
        if (
          !options.verificationEmailSender ||
          Buffer.byteLength(
              options.emailVerificationSecret || "",
              "utf8",
            ) < 32
        ) {
          throw new ApiError(
            "EMAIL_VERIFICATION_UNAVAILABLE",
            "Email verification is temporarily unavailable.",
            503,
          );
        }
        const body = await readJson(request, AUTH_BODY_LIMIT);
        const email = registrationVerificationEmail(body);
        const resendRetryAfter =
          authStore.registrationVerificationRetryAfter(email, now());
        if (resendRetryAfter > 0) {
          throw new ApiError(
            "VERIFICATION_RATE_LIMITED",
            "Please wait before requesting another verification code.",
            429,
            resendRetryAfter,
          );
        }
        const address = clientAddress(request);
        const verificationLimit = authLimiter.consume(
          [
            {
              bucket: "verify:ip",
              subject: address,
              limit: authLimits.verificationIpPerHour,
              windowMs: 60 * 60_000,
            },
            {
              bucket: "verify:email",
              subject: email,
              limit: authLimits.verificationEmailPerHour,
              windowMs: 60 * 60_000,
            },
            {
              bucket: "verify:global:minute",
              subject: "server",
              limit: authLimits.verificationGlobalPerMinute,
              windowMs: 60_000,
            },
            {
              bucket: "verify:global:hour",
              subject: "server",
              limit: authLimits.verificationGlobalPerHour,
              windowMs: 60 * 60_000,
            },
            {
              bucket: "verify:global:day",
              subject: "server",
              limit: authLimits.verificationGlobalPerDay,
              windowMs: 24 * 60 * 60_000,
            },
          ],
          now(),
        );
        if (!verificationLimit.allowed) {
          throw new ApiError(
            "VERIFICATION_RATE_LIMITED",
            "Too many verification requests. Please try again later.",
            429,
            verificationLimit.retryAfterMs,
          );
        }
        const issued = authStore.issueRegistrationVerification(
          email,
          now(),
        );
        try {
          await options.verificationEmailSender.sendRegistrationCode(
            email,
            issued.code,
          );
        } catch {
          authStore.discardRegistrationVerification(
            email,
            issued.challengeId,
            now(),
          );
          throw new ApiError(
            "EMAIL_VERIFICATION_UNAVAILABLE",
            "Email verification is temporarily unavailable.",
            503,
          );
        }
        sendJson(response, 202, {
          ok: true,
          expiresInSeconds: EMAIL_VERIFICATION_TTL_SECONDS,
          resendAfterSeconds: EMAIL_VERIFICATION_RESEND_SECONDS,
        });
        return;
      }

      if (
        request.method === "POST" &&
        (path === "/api/auth/register" || path === "/api/auth/login")
      ) {
        assertAllowedOrigin(request, options.allowedOrigins);
        const registering = path === "/api/auth/register";
        if (registering) {
          if (
            options.registrationEnabled !== true ||
            options.emailVerificationEnabled !== true
          ) {
            throw new ApiError(
              "REGISTRATION_CLOSED",
              "New account registration is currently closed.",
              403,
            );
          }
          if (
            !options.verificationEmailSender ||
            Buffer.byteLength(
                options.emailVerificationSecret || "",
                "utf8",
              ) < 32
          ) {
            throw new ApiError(
              "EMAIL_VERIFICATION_UNAVAILABLE",
              "Email verification is temporarily unavailable.",
              503,
            );
          }
        }
        const body = await readJson(request, AUTH_BODY_LIMIT);
        const email = authEmail(body);
        const address = clientAddress(request);
        const rateLimit = authLimiter.consume(
          registering
            ? [
                {
                  bucket: "register:ip",
                  subject: address,
                  limit: authLimits.registerIpPerHour,
                  windowMs: 60 * 60_000,
                },
                {
                  bucket: "register:email",
                  subject: email,
                  limit: authLimits.registerEmailPerHour,
                  windowMs: 60 * 60_000,
                },
              ]
            : [
                {
                  bucket: "login:ip",
                  subject: address,
                  limit: authLimits.loginIpPer15Minutes,
                  windowMs: 15 * 60_000,
                },
                {
                  bucket: "login:email",
                  subject: email,
                  limit: authLimits.loginEmailPer15Minutes,
                  windowMs: 15 * 60_000,
                },
              ],
          now(),
        );
        if (!rateLimit.allowed) {
          throw new ApiError(
            "AUTH_RATE_LIMITED",
            "Too many authentication attempts. Please try again later.",
            429,
            rateLimit.retryAfterMs,
          );
        }
        const session =
          registering
            ? await authStore.register(body, now)
            : await authStore.login(body, now());
        response.setHeader(
          "Set-Cookie",
          sessionCookie(
            cookieName,
            session.sessionToken,
            Math.ceil((session.expiresAt - now()) / 1000),
          ),
        );
        sendJson(response, path.endsWith("/register") ? 201 : 200, {
          ok: true,
          user: session.user,
          csrfToken: session.csrfToken,
        });
        return;
      }

      if (request.method === "POST" && path === "/api/auth/logout") {
        assertAllowedOrigin(request, options.allowedOrigins);
        await readJson(request, LOGOUT_BODY_LIMIT, true);
        const rawToken = parseCookies(request).get(cookieName) || "";
        const session = authStore.getSession(rawToken, now());
        if (session) {
          assertCsrf(request, session);
          authStore.logout(rawToken);
        }
        response.setHeader("Set-Cookie", clearSessionCookie(cookieName));
        sendJson(response, 200, { ok: true });
        return;
      }

      if (request.method === "POST" && path === "/api/action") {
        assertAllowedOrigin(request, options.allowedOrigins);
        const { session } = requireSession(
          request,
          authStore,
          cookieName,
          now(),
        );
        assertCsrf(request, session);
        const actionRateLimit = authLimiter.consume(
          [
            {
              bucket: "action:user",
              subject: session.user.id,
              limit: options.actionRequestsPerMinute || 240,
              windowMs: 60_000,
            },
          ],
          now(),
        );
        if (!actionRateLimit.allowed) {
          throw new ApiError(
            "RATE_LIMITED",
            "Too many API requests. Please try again shortly.",
            429,
            actionRateLimit.retryAfterMs,
          );
        }
        const body = await readJson(request, ACTION_BODY_LIMIT);
        const service = createBackendService({
          store: learningStore,
          scorer,
          getTrustedUid: () => session.user.id,
          now,
          scoreLimitPerMinute: options.scoreLimitPerMinute || 10,
        });
        sendJson(response, 200, await service.handle(body));
        return;
      }

      if (path.startsWith("/api/")) {
        throw new ApiError(
          "ROUTE_NOT_FOUND",
          "The requested API route does not exist.",
          404,
        );
      }
      throw new ApiError(
        "ROUTE_NOT_FOUND",
        "This server exposes API routes only.",
        404,
      );
    } catch (error) {
      const status = error instanceof ApiError ? error.status : 500;
      if (error instanceof ApiError && error.retryAfterMs != null) {
        response.setHeader(
          "Retry-After",
          Math.max(1, Math.ceil(error.retryAfterMs / 1000)),
        );
      }
      if (!(error instanceof ApiError)) {
        // Never log request bodies, passwords, learner answers, cookies, or keys.
        console.error("my-english-api internal error", {
          name: error instanceof Error ? error.name : "UnknownError",
        });
      }
      sendJson(response, status, errorResponse(error));
    }
  });

  server.requestTimeout = 30_000;
  server.headersTimeout = 10_000;
  server.keepAliveTimeout = 5_000;
  return server;
}

export function startServerFromEnvironment(): {
  server: Server;
  database: SqliteDatabase;
} {
  const config = loadRuntimeConfig();
  const database = openDatabase(config.databasePath);
  const server = createAppServer({
    database,
    allowedOrigins: config.allowedOrigins,
    cookieName: config.cookieName,
    registrationEnabled: config.registrationEnabled,
    emailVerificationEnabled: config.emailVerificationEnabled,
    emailVerificationSecret: config.emailVerificationSecret,
    verificationEmailSender: config.smtp
      ? new NodemailerRegistrationVerificationEmailSender(config.smtp)
      : undefined,
    sessionTtlDays: config.sessionTtlDays,
    passwordWork: config.passwordWork,
    scoreLimitPerMinute: config.scoreLimitPerMinute,
    actionRequestsPerMinute: config.actionRequestsPerMinute,
    authRateLimits: config.authRateLimits,
    learningQuotas: config.learningQuotas,
    llmGlobalLimits: config.llmGlobalLimits,
  });
  server.listen(config.port, config.host, () => {
    console.log(
      `my-english-api listening on http://${config.host}:${config.port}`,
    );
  });

  let stopping = false;
  const stop = (): void => {
    if (stopping) return;
    stopping = true;
    server.close(() => {
      database.close();
      process.exit(0);
    });
    setTimeout(() => process.exit(1), 10_000).unref();
  };
  process.once("SIGTERM", stop);
  process.once("SIGINT", stop);
  return { server, database };
}

if (require.main === module) {
  startServerFromEnvironment();
}
