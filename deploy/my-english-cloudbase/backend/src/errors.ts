export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly retryAfterMs?: number;

  constructor(
    code: string,
    message: string,
    status = 400,
    retryAfterMs?: number,
  ) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.retryAfterMs = retryAfterMs;
  }
}

export interface ErrorResponse {
  ok: false;
  code: string;
  message: string;
  retryAfterMs?: number;
  error: {
    code: string;
    message: string;
    retryAfterMs?: number;
  };
}

export function errorResponse(error: unknown): ErrorResponse {
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
