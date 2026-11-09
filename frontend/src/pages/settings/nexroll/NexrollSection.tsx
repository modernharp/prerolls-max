// Settings > Moving from NeXroll. Says plainly that Prerolls Max replaces
// NeXroll, brings a NeXroll setup over, and (advanced) lets both run side by
// side with each media server left to one of them.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../../../lib/api";
import { isAdminOnly } from "../../../lib/errors";
import { nexrollKeys, useMigrateStatus, type AlongsideState } from "../../../lib/nexroll";
import { ErrorNotice, Loading, Notice } from "../../../components/Notice";
import { NexrollAlongside } from "./NexrollAlongside";
import { NexrollImport } from "./NexrollImport";

export function ReplacesNexroll() {
  return (
    <Notice tone="info" title="Prerolls Max replaces NeXroll. Use one or the other.">
      <p>
        Both write Plex's intro list, so they'd keep overwriting each other. On Jellyfin and Emby both plugins add intros, so every movie gets two sets.
        Stop NeXroll and remove its plugin, and bring your setup over below. <Link to="/help/moving-from-nexroll">How to move, step by step</Link>
      </p>
    </Notice>
  );
}

export function NexrollSection() {
  const queryClient = useQueryClient();
  const status = useMigrateStatus();
  const mode = status.data?.alongside.mode ?? "replace";
  const setMode = useMutation({
    mutationFn: (next: "replace" | "alongside") => api.put<AlongsideState>("/api/migrate/nexroll/alongside", { mode: next }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: nexrollKeys.status });
      await queryClient.invalidateQueries({ queryKey: nexrollKeys.detect });
      await queryClient.invalidateQueries({ queryKey: ["media-servers"] });
    },
  });

  if (status.isError && isAdminOnly(status.error)) {
    return (
      <div className="stack">
        <ReplacesNexroll />
        <p className="muted">Only an admin can import from NeXroll or change how the two run.</p>
      </div>
    );
  }
  return (
    <div className="stack">
      <ReplacesNexroll />
      {status.isLoading && <Loading />}
      {status.isError && <ErrorNotice error={status.error} onRetry={() => status.refetch()} />}
      {status.data && (
        <>
          <fieldset className="plain-fieldset">
            <legend className="field-label">NeXroll on this network</legend>
            <div className="choice-grid">
              <label className="choice">
                <input type="radio" name="nx-plan" checked={mode === "replace"} disabled={setMode.isPending} onChange={() => setMode.mutate("replace")} />
                <span>
                  <span className="choice-title">Replace NeXroll</span>
                  <span className="choice-desc">Prerolls Max looks after every media server. Recommended.</span>
                </span>
              </label>
              <label className="choice">
                <input type="radio" name="nx-plan" checked={mode === "alongside"} disabled={setMode.isPending} onChange={() => setMode.mutate("alongside")} />
                <span>
                  <span className="choice-title">Keep NeXroll running too (advanced)</span>
                  <span className="choice-desc">Each media server is managed by one app only. Prerolls Max needs its own port.</span>
                </span>
              </label>
            </div>
          </fieldset>
          {setMode.isError && <ErrorNotice error={setMode.error} />}
          {mode === "alongside" && <NexrollAlongside state={status.data.alongside} />}
          <h3>Bring your NeXroll setup over</h3>
          <p className="muted">
            Collections, intro videos, schedules, playlists and media servers. You'll see what's there before anything changes. NeXroll's user accounts and
            API keys stay behind.
          </p>
          <NexrollImport />
        </>
      )}
    </div>
  );
}
