import cloudbase from "@cloudbase/js-sdk";
import { errorResponse } from "./errors";
import { OpenAiCompatibleAnswerScorer } from "./llm";
import { createBackendService } from "./service";
import {
  CloudBaseLearningStore,
  type CloudBaseDatabase,
} from "./store";

type RuntimeContext = Record<string, unknown>;

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function uidFromRuntimeContext(context: RuntimeContext): string {
  const auth =
    context.auth && typeof context.auth === "object"
      ? (context.auth as Record<string, unknown>)
      : {};
  const userInfo =
    context.userInfo && typeof context.userInfo === "object"
      ? (context.userInfo as Record<string, unknown>)
      : {};
  return text(auth.uid) || text(userInfo.uid) || text(context.uid);
}

export async function main(
  event: unknown,
  contextValue: unknown,
): Promise<Record<string, unknown>> {
  if (
    event != null &&
    typeof event === "object" &&
    !Array.isArray(event) &&
    (event as { action?: unknown }).action === "health"
  ) {
    return {
      ok: true,
      service: "my-english-api",
      version: "0.1.0",
      serverTime: new Date().toISOString(),
    };
  }

  const context =
    contextValue != null &&
    typeof contextValue === "object" &&
    !Array.isArray(contextValue)
      ? (contextValue as RuntimeContext)
      : {};
  try {
    // In an SCF environment js-sdk v3 resolves the current CloudBase
    // environment and temporary administrator credential when env is omitted.
    // The invocation context remains the trusted fallback for caller identity.
    const app = cloudbase.init({});
    const store = new CloudBaseLearningStore(
      app.database() as CloudBaseDatabase,
    );
    const scorer = OpenAiCompatibleAnswerScorer.fromEnvironment();
    const service = createBackendService({
      store,
      scorer,
      scoreLimitPerMinute:
        Number(process.env.LLM_RATE_LIMIT_PER_MINUTE) || 10,
      getTrustedUid: () => {
        try {
          const sdkUid = text(app.auth.getUserInfo().uid);
          if (sdkUid) return sdkUid;
        } catch {
          // A normal function call can still expose auth on the trusted
          // runtime context even when the SDK helper is unavailable.
        }
        return uidFromRuntimeContext(context);
      },
    });
    return (await service.handle(event)) as Record<string, unknown>;
  } catch (error) {
    if (!(error instanceof Error) || error.name !== "ApiError") {
      // Do not log the event, learner answer, provider body, or API key.
      console.error("my-english-api internal error", {
        name: error instanceof Error ? error.name : "UnknownError",
      });
    }
    return errorResponse(error) as unknown as Record<string, unknown>;
  }
}
