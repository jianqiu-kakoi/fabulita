"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.ApiError = void 0;
exports.errorResponse = errorResponse;
class ApiError extends Error {
    code;
    status;
    retryAfterMs;
    constructor(code, message, status = 400, retryAfterMs) {
        super(message);
        this.name = "ApiError";
        this.code = code;
        this.status = status;
        this.retryAfterMs = retryAfterMs;
    }
}
exports.ApiError = ApiError;
function errorResponse(error) {
    if (error instanceof ApiError) {
        const details = {
            code: error.code,
            message: error.message,
            ...(error.retryAfterMs == null
                ? {}
                : { retryAfterMs: error.retryAfterMs }),
        };
        return {
            ok: false,
            ...details,
            error: details,
        };
    }
    return {
        ok: false,
        code: "INTERNAL_ERROR",
        message: "The service could not complete this request.",
        error: {
            code: "INTERNAL_ERROR",
            message: "The service could not complete this request.",
        },
    };
}
