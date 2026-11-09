// Upload list helpers, ported from the old interface (utils/uploadQueue.js).
// Files are keyed by name, size and modified time, so picking the same file
// twice doesn't queue it twice. Type and size are checked before sending.
//
// Like the upload lists in Google Drive or Dropbox, every file gets a row with
// its own status. A file that can't be added (not a video, too big, or turned
// down by the server) stays in the list as "Not added" with its reason, is
// never sent again, and doesn't count towards the Upload button.
import { ApiError, NETWORK_ERROR, UNEXPECTED_REPLY, errorFromResponse } from "./errors";
import { recordError } from "./lastError";

/** Matches MAX_PREROLL_UPLOAD_SIZE in backend/preroll_files.py. */
export const MAX_UPLOAD_BYTES = 500 * 1024 * 1024;

export const VIDEO_EXTENSIONS = [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".ts", ".mpg", ".mpeg"];

export const fileKey = (file: File) => `${file.name}:${file.size}:${file.lastModified}`;

export const isVideoFile = (file: File) => {
  const name = file.name.toLowerCase();
  return file.type.startsWith("video/") || VIDEO_EXTENSIONS.some((ext) => name.endsWith(ext));
};

export const isTooLarge = (file: File) => file.size > MAX_UPLOAD_BYTES;

export const NOT_A_VIDEO = "not a video file.";
export const TOO_BIG = "bigger than 500 MB, the most one intro can be.";

export interface MergeResult {
  files: File[];
  /** Files added to the list that can't be sent, by fileKey, with the reason. */
  refused: Record<string, string>;
  notVideo: string[];
  tooLarge: string[];
  repeated: number;
}

/** Adds picked or dropped files to the list. Files that can't be sent are
 * listed too, with the reason, so the person sees why they were left out. */
export function mergeFiles(existing: File[], incoming: Iterable<File>): MergeResult {
  const files = [...existing];
  const seen = new Set(files.map(fileKey));
  const refused: Record<string, string> = {};
  const notVideo: string[] = [];
  const tooLarge: string[] = [];
  let repeated = 0;
  for (const file of incoming) {
    const key = fileKey(file);
    if (seen.has(key)) {
      repeated += 1;
      continue;
    }
    seen.add(key);
    files.push(file);
    if (!isVideoFile(file)) {
      notVideo.push(file.name);
      refused[key] = NOT_A_VIDEO;
    } else if (isTooLarge(file)) {
      tooLarge.push(file.name);
      refused[key] = TOO_BIG;
    }
  }
  return { files, refused, notVideo, tooLarge, repeated };
}

export type UploadState =
  | { status: "waiting" }
  | { status: "sending"; percent: number }
  | { status: "processing" }
  | { status: "done" }
  | { status: "skipped"; message: string }
  /** Can't be added: never sent (again), shown as "Not added". */
  | { status: "refused"; message: string }
  /** The exact same video is already in the library: Skip (the default) or Add anyway. */
  | { status: "duplicate"; token: string; existing: string; busy?: "add" | "skip" }
  /** Didn't get through (network, server busy): sent again on the next Upload. */
  | { status: "error"; error: ApiError };

export const isFinished = (s?: UploadState) => s?.status === "done" || s?.status === "skipped";

/** Done with this file one way or another: nothing more to send. A
 * duplicate counts as settled: closing the list skips it. */
export const isSettled = (s?: UploadState) => isFinished(s) || s?.status === "refused" || s?.status === "duplicate";

/** What the server answers for one upload (or a web-link job's result). */
export interface UploadAnswer {
  uploaded?: boolean;
  skipped?: boolean;
  message?: string;
  duplicate?: boolean;
  token?: string;
  existing?: { id: number; name: string };
  filename?: string;
}

/** The row state an upload answer leads to. */
export function stateFromAnswer(res: UploadAnswer | undefined): UploadState {
  if (res?.duplicate && res.token) return { status: "duplicate", token: res.token, existing: res.existing?.name ?? "" };
  if (res?.skipped) return { status: "skipped", message: res.message ?? "Already in your library." };
  return { status: "done" };
}

/** Waiting to go, or worth trying again. */
export const canSend = (s?: UploadState) => !s || s.status === "waiting" || s.status === "error";

/** The server turned down the file itself (wrong type, too big, not a real
 * video), so sending it again would give the same answer. */
export const isRefusal = (error: unknown) =>
  error instanceof ApiError && [400, 413, 415, 422].includes(error.status);

function parseJson(text: string): { ok: boolean; value: unknown } {
  try {
    return { ok: true, value: text ? JSON.parse(text) : undefined };
  } catch {
    return { ok: false, value: undefined };
  }
}

/**
 * Sends one file with XMLHttpRequest, which (unlike fetch) reports upload
 * progress. Resolves with the server's JSON; rejects with an ApiError.
 */
export function sendUpload(
  url: string,
  form: FormData,
  { onProgress, onSent }: { onProgress?: (percent: number) => void; onSent?: () => void } = {},
): { promise: Promise<unknown>; abort: () => void } {
  const xhr = new XMLHttpRequest();
  const promise = new Promise<unknown>((resolve, reject) => {
    xhr.open("POST", url);
    xhr.withCredentials = true;
    xhr.setRequestHeader("Accept", "application/json");
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) onProgress((event.loaded / event.total) * 100);
    };
    xhr.upload.onload = () => onSent?.();
    xhr.onload = () => {
      const body = parseJson(xhr.responseText);
      if (xhr.status >= 200 && xhr.status < 300) {
        if (body.ok) resolve(body.value);
        else reject(UNEXPECTED_REPLY(xhr.status));
        return;
      }
      const error = body.ok
        ? errorFromResponse(xhr.status, body.value, xhr.getResponseHeader("x-request-id"))
        : errorFromResponse(xhr.status, undefined);
      recordError(error, url);
      reject(error);
    };
    xhr.onerror = () => reject(NETWORK_ERROR());
    xhr.onabort = () => reject(new ApiError({ kind: "other", message: "Upload cancelled." }));
    xhr.send(form);
  });
  return { promise, abort: () => xhr.abort() };
}
