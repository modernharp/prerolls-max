// Remembers the most recent error so Help > Report a problem can quote it.
import { useSyncExternalStore } from "react";
import type { ApiError } from "./errors";

export interface LastError {
  message: string;
  requestId?: string;
  path: string;
  at: string;
}

let last: LastError | null = null;
const listeners = new Set<() => void>();

export function recordError(error: ApiError, path: string): void {
  last = { message: error.message, requestId: error.requestId, path, at: new Date().toISOString() };
  listeners.forEach((fn) => fn());
}

function subscribe(fn: () => void) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function useLastError(): LastError | null {
  return useSyncExternalStore(subscribe, () => last, () => last);
}
