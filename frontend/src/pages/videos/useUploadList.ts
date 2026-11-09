// The upload list behind UploadDialog: which files are in it, what happened to
// each, and sending the ones that can be sent.
import { useCallback, useState } from "react";
import { api } from "../../lib/api";
import { describeError } from "../../lib/errors";
import { plural } from "../../lib/format";
import {
  canSend, fileKey, isRefusal, isSettled, mergeFiles, sendUpload, stateFromAnswer,
  type UploadAnswer, type UploadState,
} from "../../lib/uploadQueue";

/** "That file is..." reads as "Not added — that file is...". */
export const reasonText = (message: string) => (/^[A-Z][a-z]/.test(message) ? message[0]!.toLowerCase() + message.slice(1) : message);

/** Skip or add a video that matched one already in the library. */
export const resolveDuplicate = (token: string, action: "add" | "skip") =>
  api.post<UploadAnswer>(`/prerolls/upload/staged/${encodeURIComponent(token)}`, { action });

export function useUploadList() {
  const [files, setFiles] = useState<File[]>([]);
  const [states, setStates] = useState<Record<string, UploadState>>({});
  const [note, setNote] = useState<string>();

  const setState = useCallback((file: File, state: UploadState) => setStates((s) => ({ ...s, [fileKey(file)]: state })), []);

  /** Adds picked or dropped files; ``reset`` starts a new list. */
  const add = (incoming: Iterable<File>, reset = false) => {
    const result = mergeFiles(reset ? [] : files, incoming);
    const refused: Record<string, UploadState> = {};
    for (const [key, message] of Object.entries(result.refused)) refused[key] = { status: "refused", message };
    setFiles(result.files);
    setStates((s) => ({ ...(reset ? {} : s), ...refused }));
    setNote(result.repeated ? `${plural(result.repeated, "file")} already in the list.` : undefined);
  };

  const remove = (file: File) => {
    setFiles((list) => list.filter((f) => f !== file));
    setStates(({ [fileKey(file)]: _gone, ...rest }) => rest);
  };

  const clear = () => {
    skipWaitingDuplicates();
    setFiles([]);
    setStates({});
    setNote(undefined);
  };

  /** Closing the list means Skip for duplicates nobody answered. */
  const skipWaitingDuplicates = () => {
    for (const state of Object.values(states)) {
      if (state.status === "duplicate" && !state.busy) void resolveDuplicate(state.token, "skip").catch(() => undefined);
    }
  };

  const choose = async (file: File, action: "add" | "skip") => {
    const state = states[fileKey(file)];
    if (state?.status !== "duplicate") return false;
    setState(file, { ...state, busy: action });
    try {
      const res = await resolveDuplicate(state.token, action);
      if (action === "skip") setState(file, { status: "skipped", message: `Skipped. It's already in your library as "${state.existing}".` });
      else setState(file, stateFromAnswer(res));
      return action === "add";
    } catch (error) {
      setState(file, { status: "refused", message: reasonText(`${describeError(error).message} ${describeError(error).hint ?? ""}`.trim()) });
      return false;
    }
  };

  /** Sends every file that can be sent, one at a time. Returns how many were added. */
  const send = async (categoryId: string) => {
    let added = 0;
    for (const file of files.filter((f) => canSend(states[fileKey(f)]))) {
      const form = new FormData();
      form.append("file", file);
      form.append("if_duplicate", "ask");
      if (categoryId) form.append("category_id", categoryId);
      setState(file, { status: "sending", percent: 0 });
      try {
        const { promise } = sendUpload("/prerolls/upload", form, {
          onProgress: (percent) => setState(file, { status: "sending", percent }),
          onSent: () => setState(file, { status: "processing" }),
        });
        const next = stateFromAnswer((await promise) as UploadAnswer | undefined);
        setState(file, next);
        if (next.status === "done") added += 1;
      } catch (error) {
        // A file the server turned down won't be sent again; anything else
        // (no network, a restart) is tried again on the next Upload.
        if (isRefusal(error)) setState(file, { status: "refused", message: reasonText(describeError(error).message) });
        else setState(file, { status: "error", error: error as never });
      }
    }
    return added;
  };

  const sendable = files.filter((f) => canSend(states[fileKey(f)])).length;
  const settled = files.length > 0 && files.every((f) => isSettled(states[fileKey(f)]));
  const waitingChoice = files.some((f) => states[fileKey(f)]?.status === "duplicate");
  return { files, states, note, add, remove, clear, choose, send, sendable, settled, waitingChoice, skipWaitingDuplicates };
}
