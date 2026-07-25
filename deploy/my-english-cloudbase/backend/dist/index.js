"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.main = main;
const js_sdk_1 = __importDefault(require("@cloudbase/js-sdk"));
const errors_1 = require("./errors");
const llm_1 = require("./llm");
const service_1 = require("./service");
const store_1 = require("./store");
function text(value) {
    return typeof value === "string" ? value.trim() : "";
}
function uidFromRuntimeContext(context) {
    const auth = context.auth && typeof context.auth === "object"
        ? context.auth
        : {};
    const userInfo = context.userInfo && typeof context.userInfo === "object"
        ? context.userInfo
        : {};
    return text(auth.uid) || text(userInfo.uid) || text(context.uid);
}
async function main(event, contextValue) {
    if (event != null &&
        typeof event === "object" &&
        !Array.isArray(event) &&
        event.action === "health") {
        return {
            ok: true,
            service: "my-english-api",
            version: "0.1.0",
            serverTime: new Date().toISOString(),
        };
    }
    const context = contextValue != null &&
        typeof contextValue === "object" &&
        !Array.isArray(contextValue)
        ? contextValue
        : {};
    try {
        // In an SCF environment js-sdk v3 resolves the current CloudBase
        // environment and temporary administrator credential when env is omitted.
        // The invocation context remains the trusted fallback for caller identity.
        const app = js_sdk_1.default.init({});
        const store = new store_1.CloudBaseLearningStore(app.database());
        const scorer = llm_1.OpenAiCompatibleAnswerScorer.fromEnvironment();
        const service = (0, service_1.createBackendService)({
            store,
            scorer,
            scoreLimitPerMinute: Number(process.env.LLM_RATE_LIMIT_PER_MINUTE) || 10,
            getTrustedUid: () => {
                try {
                    const sdkUid = text(app.auth.getUserInfo().uid);
                    if (sdkUid)
                        return sdkUid;
                }
                catch {
                    // A normal function call can still expose auth on the trusted
                    // runtime context even when the SDK helper is unavailable.
                }
                return uidFromRuntimeContext(context);
            },
        });
        return (await service.handle(event));
    }
    catch (error) {
        if (!(error instanceof Error) || error.name !== "ApiError") {
            // Do not log the event, learner answer, provider body, or API key.
            console.error("my-english-api internal error", {
                name: error instanceof Error ? error.name : "UnknownError",
            });
        }
        return (0, errors_1.errorResponse)(error);
    }
}
