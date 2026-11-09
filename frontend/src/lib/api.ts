// The one way this interface talks to the Prerolls Max server.
// JSON in and out, the sign-in cookie sent along, a timeout on every call,
// and every failure turned into an ApiError (see errors.ts).
import {
  ApiError,
  NETWORK_ERROR,
  TIMEOUT_ERROR,
  UNEXPECTED_REPLY,
  errorFromResponse,
} from "./errors";
import { recordError } from "./lastError";

export type Query = Record<string, string | number | boolean | null | undefined>;

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE" | "PATCH";
  body?: unknown;
  query?: Query;
  /** Milliseconds before giving up. Default 20 s. */
  timeoutMs?: number;
  signal?: AbortSignal;
  /** Don't tell the rest of the app about a 401 (the sign-in form handles its own). */
  quietAuth?: boolean;
}

type AuthListener = (error: ApiError) => void;
const authListeners = new Set<AuthListener>();

/** Called whenever the server says "sign in" or "set up first". */
export function onAuthProblem(listener: AuthListener): () => void {
  authListeners.add(listener);
  return () => authListeners.delete(listener);
}

export function buildUrl(path: string, query?: Query): string {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${path}${path.includes("?") ? "&" : "?"}${qs}` : path;
}

async function readBody(response: Response): Promise<{ json: unknown; isJson: boolean; empty: boolean }> {
  const text = await response.text();
  if (!text.trim()) return { json: undefined, isJson: false, empty: true };
  const type = response.headers.get("content-type") ?? "";
  if (type.includes("json") || /^[[{"]/.test(text.trim())) {
    try {
      return { json: JSON.parse(text), isJson: true, empty: false };
    } catch {
      return { json: undefined, isJson: false, empty: false };
    }
  }
  return { json: undefined, isJson: false, empty: false };
}

export function reportApiError(error: ApiError, path: string): void {
  if (error.kind === "signed_out" || error.kind === "setup_required") {
    authListeners.forEach((fn) => fn(error));
    return;
  }
  recordError(error, path);
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, query, timeoutMs = 20_000, signal, quietAuth } = options;
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const onOuterAbort = () => controller.abort();
  signal?.addEventListener("abort", onOuterAbort);

  const headers: Record<string, string> = { Accept: "application/json" };
  let payload: BodyInit | undefined;
  if (body instanceof FormData) {
    payload = body;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      headers,
      body: payload,
      credentials: "same-origin",
      signal: controller.signal,
    });
  } catch (cause) {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onOuterAbort);
    if (signal?.aborted) throw cause;
    const error = timedOut ? TIMEOUT_ERROR() : NETWORK_ERROR();
    recordError(error, path);
    throw error;
  }

  try {
    const { json, isJson, empty } = await readBody(response);
    if (response.ok) {
      if (isJson || empty) return json as T;
      const odd = UNEXPECTED_REPLY(response.status);
      recordError(odd, path);
      throw odd;
    }
    const error = isJson || empty
      ? errorFromResponse(response.status, json, response.headers.get("x-request-id"))
      : response.status >= 500 || response.status === 404
        ? errorFromResponse(response.status, undefined, response.headers.get("x-request-id"))
        : UNEXPECTED_REPLY(response.status);
    if (!(quietAuth && error.status === 401)) reportApiError(error, path);
    throw error;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (timedOut) throw TIMEOUT_ERROR();
    throw NETWORK_ERROR();
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onOuterAbort);
  }
}

export const api = {
  get: <T>(path: string, query?: Query, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "GET", query }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "POST", body }),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "PUT", body }),
  del: <T>(path: string, options?: RequestOptions) => request<T>(path, { ...options, method: "DELETE" }),
};
