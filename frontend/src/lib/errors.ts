// One error type for everything that can go wrong talking to Prerolls Max.
// Every failure (no network, a timeout, an HTML page where JSON was expected,
// a 401, a form problem, a crash on the server) becomes an ApiError with a
// plain message, a hint about what to do, per-field messages and the request
// id a bug report can quote. See docs/dev/CONTRACTS.md §1.

export type ApiErrorKind =
  | "network"
  | "timeout"
  | "unexpected"
  | "signed_out"
  | "setup_required"
  | "forbidden"
  | "not_found"
  | "invalid"
  | "conflict"
  | "rate_limited"
  | "server"
  | "upstream"
  | "other";

export interface ApiErrorInit {
  kind: ApiErrorKind;
  message: string;
  hint?: string;
  status?: number;
  code?: string;
  fields?: Record<string, string>;
  requestId?: string;
}

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly hint?: string;
  readonly status: number;
  readonly code: string;
  readonly fields: Record<string, string>;
  readonly requestId?: string;

  constructor(init: ApiErrorInit) {
    super(init.message);
    this.name = "ApiError";
    this.kind = init.kind;
    this.hint = init.hint;
    this.status = init.status ?? 0;
    this.code = init.code ?? init.kind;
    this.fields = init.fields ?? {};
    this.requestId = init.requestId;
  }
}

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError;
}

/** True when the server doesn't have this feature yet (older or newer backend). */
export function isMissingFeature(error: unknown): boolean {
  return isApiError(error) && (error.status === 404 || error.status === 405);
}

const GENERIC: Record<number, { kind: ApiErrorKind; message: string; hint: string }> = {
  400: { kind: "invalid", message: "Prerolls Max couldn't use what was sent.", hint: "Check the form and try again." },
  401: { kind: "signed_out", message: "You're signed out.", hint: "Sign in again to carry on." },
  403: { kind: "forbidden", message: "You don't have permission to do that.", hint: "Ask the person who set up Prerolls Max to do it, or to make you an admin." },
  404: { kind: "not_found", message: "That isn't there anymore.", hint: "Refresh the page to see what's there now." },
  409: { kind: "conflict", message: "That clashes with something that already exists.", hint: "Pick a different name and try again." },
  413: { kind: "invalid", message: "That file is too big.", hint: "Intro videos can be up to 500 MB." },
  422: { kind: "invalid", message: "Some of the details need fixing.", hint: "Check the highlighted fields." },
  429: { kind: "rate_limited", message: "Too many tries in a short time.", hint: "Wait a minute, then try again." },
  502: { kind: "upstream", message: "Another service didn't answer Prerolls Max.", hint: "Check that your media server is running, then try again." },
  503: { kind: "server", message: "Prerolls Max is busy starting up or updating.", hint: "Wait a moment, then try again." },
  504: { kind: "upstream", message: "Another service took too long to answer.", hint: "Check that your media server is running, then try again." },
};

const SERVER_FALLBACK = {
  kind: "server" as const,
  message: "Something went wrong inside Prerolls Max.",
  hint: "Try again. If it keeps happening, report it with the code below.",
};

export const NETWORK_ERROR = () =>
  new ApiError({
    kind: "network",
    message: "Can't reach Prerolls Max.",
    hint: "Check that it's still running and that this device is on the same network, then try again.",
  });

export const TIMEOUT_ERROR = () =>
  new ApiError({
    kind: "timeout",
    message: "Prerolls Max is taking too long to answer.",
    hint: "It may be busy. Wait a moment, then try again.",
  });

export const UNEXPECTED_REPLY = (status: number) =>
  new ApiError({
    kind: "unexpected",
    status,
    message: "Prerolls Max sent back something this page can't read.",
    hint: "If you reach Prerolls Max through a reverse proxy, check that it passes requests straight through. Otherwise reload the page.",
  });

// Messages from older endpoints sometimes carry exception text. Show those
// only when they read like a sentence, never stack traces or Python reprs.
const TECHNICAL = /traceback|exception|errno|\bnone\b|object at 0x|\{|\}|\[|\]|sqlalchemy|pydantic|httpx|http error|status code|<[a-z]/i;

export function looksTechnical(text: string): boolean {
  return text.length > 300 || TECHNICAL.test(text);
}

interface ErrorBody {
  detail?: unknown;
  message?: unknown;
  error?: {
    code?: string;
    message?: string;
    hint?: string;
    fields?: Record<string, string>;
    request_id?: string;
  };
}

/** FastAPI's own 422 list: [{loc: ["body", "url"], msg}] -> {url: msg}. */
function fieldsFromDetailList(detail: unknown): Record<string, string> | undefined {
  if (!Array.isArray(detail)) return undefined;
  const fields: Record<string, string> = {};
  for (const item of detail) {
    if (!item || typeof item !== "object") continue;
    const loc = (item as { loc?: unknown[] }).loc;
    const msg = (item as { msg?: unknown }).msg;
    if (!Array.isArray(loc) || typeof msg !== "string") continue;
    const name = loc.filter((p) => p !== "body" && p !== "query").join(".");
    if (name) fields[name] = msg.replace(/^Value error, /, "");
  }
  return Object.keys(fields).length ? fields : undefined;
}

/** Turns an HTTP error status plus whatever body came back into an ApiError. */
export function errorFromResponse(status: number, body: unknown, requestIdHeader?: string | null): ApiError {
  const generic = GENERIC[status] ?? (status >= 500 ? SERVER_FALLBACK : { kind: "other" as const, message: "That didn't work.", hint: "Try again." });
  const data = (body && typeof body === "object" ? body : {}) as ErrorBody;
  const err = data.error;
  const requestId = err?.request_id ?? requestIdHeader ?? undefined;

  if (err && typeof err.message === "string") {
    const code = err.code ?? generic.kind;
    let kind: ApiErrorKind = generic.kind;
    if (code === "setup_required") kind = "setup_required";
    return new ApiError({
      kind,
      status,
      code,
      message: err.message,
      hint: err.hint ?? (status >= 500 ? generic.hint : undefined),
      fields: err.fields,
      requestId,
    });
  }

  const fields = fieldsFromDetailList(data.detail);
  const raw = typeof data.detail === "string" ? data.detail : typeof data.message === "string" ? data.message : "";
  const bareAuth = status === 401 && /^(authentication required|not authenticated)\.?$/i.test(raw.trim());
  const usable = raw && !looksTechnical(raw) && status < 500 && !bareAuth;
  return new ApiError({
    kind: generic.kind,
    status,
    message: usable ? raw : generic.message,
    hint: generic.hint,
    fields,
    requestId,
  });
}

/** A 403 because the signed-in person isn't an admin (not "this collection is locked"). */
export function isAdminOnly(error: unknown): boolean {
  if (!isApiError(error) || error.status !== 403) return false;
  return error.code === "forbidden" || /admin/i.test(error.code) || /admin/i.test(error.message);
}

/** Anything thrown -> a message a person can read. */
export function describeError(error: unknown): { message: string; hint?: string; requestId?: string } {
  if (isAdminOnly(error)) {
    return {
      message: "Only an admin can change this.",
      hint: "Sign in with an admin account, or ask the person who set up Prerolls Max to do it.",
      requestId: (error as ApiError).requestId,
    };
  }
  if (isApiError(error)) return { message: error.message, hint: error.hint, requestId: error.requestId };
  return { message: "Something went wrong on this page.", hint: "Reload the page and try again." };
}
