// "Keep NeXroll running too (advanced)": another port for Prerolls Max, and
// which app manages each media server. Both apps write Plex's one intro list
// and both plugins add intros, so each server must be left to exactly one.
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../../lib/api";
import { ApiError } from "../../../lib/errors";
import { addressWithPort, checkPort, nexrollKeys, type AlongsideState, type Manager } from "../../../lib/nexroll";
import { Button } from "../../../components/Button";
import { TextField } from "../../../components/Field";
import { ErrorNotice, Notice } from "../../../components/Notice";
import { useToast } from "../../../components/Toast";

const TYPE_LABEL = { plex: "Plex", jellyfin: "Jellyfin", emby: "Emby" } as const;

function PortSetting({ state }: { state: AlongsideState }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { port } = state;
  const [value, setValue] = useState(String(port.saved ?? (port.running === 9393 ? 9494 : port.running)));
  const [touched, setTouched] = useState(false);
  const localError = touched ? checkPort(value, state.mode === "alongside") : undefined;
  const save = useMutation({
    mutationFn: () => api.put<AlongsideState>("/api/migrate/nexroll/alongside", { port: Number(value) }),
    onSuccess: async (saved) => {
      queryClient.setQueryData(nexrollKeys.status, (old: unknown) => (old ? { ...(old as object), alongside: saved } : old));
      await queryClient.invalidateQueries({ queryKey: nexrollKeys.status });
      toast({ tone: "success", title: `Saved. Prerolls Max uses port ${value} after a restart.` });
    },
  });
  const serverError = save.error instanceof ApiError ? save.error.fields.port : undefined;

  if (port.source === "environment" || port.in_docker) {
    return (
      <Notice tone="info" title={`Prerolls Max listens on port ${port.running}.`}>
        {port.in_docker ? (
          <p>
            In Docker, leave the port inside the container alone and change the port mapping instead, for example <code>9494:9393</code> in{" "}
            <code>docker-compose.yml</code> or the Unraid template. NeXroll keeps 9393.
          </p>
        ) : (
          <p>The port comes from PMAX_PORT, which always wins. Change or remove PMAX_PORT where Prerolls Max is started.</p>
        )}
      </Notice>
    );
  }
  return (
    <form
      className="stack-sm"
      onSubmit={(e) => {
        e.preventDefault();
        setTouched(true);
        if (!checkPort(value, state.mode === "alongside")) save.mutate();
      }}
    >
      <TextField
        label="Prerolls Max's port"
        help={`Prerolls Max listens on ${port.running} now. NeXroll uses 9393, so pick another one, like 9494.`}
        inputMode="numeric"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={() => setTouched(true)}
        error={localError ?? serverError}
        className="input-short"
      />
      <div className="form-actions">
        <Button type="submit" loading={save.isPending}>
          Save port
        </Button>
      </div>
      {save.isError && !serverError && <ErrorNotice error={save.error} />}
    </form>
  );
}

function ServerTable({ state }: { state: AlongsideState }) {
  const queryClient = useQueryClient();
  const set = useMutation({
    mutationFn: ({ id, manager }: { id: number; manager: Manager }) => api.put(`/api/servers/${id}/manager`, { manager }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: nexrollKeys.status });
      await queryClient.invalidateQueries({ queryKey: nexrollKeys.detect });
      await queryClient.invalidateQueries({ queryKey: ["media-servers"] });
    },
  });
  if (!state.servers.length) return <p className="muted">Connect your media servers first; then pick who manages each one here.</p>;
  return (
    <div className="table-wrap">
      <table className="table">
        <caption className="visually-hidden">Which app manages intros on each media server</caption>
        <thead>
          <tr>
            <th scope="col">Server</th>
            <th scope="col">Intros managed by</th>
          </tr>
        </thead>
        <tbody>
          {state.servers.map((s) => (
            <tr key={s.id}>
              <th scope="row">
                {s.name} <span className="muted small">({TYPE_LABEL[s.type]})</span>
              </th>
              <td>
                <select
                  className="input"
                  aria-label={`Who manages intros on ${s.name}`}
                  value={s.manager}
                  disabled={set.isPending}
                  onChange={(e) => set.mutate({ id: s.id, manager: e.target.value as Manager })}
                >
                  <option value="prerollsmax">Prerolls Max</option>
                  <option value="nexroll">NeXroll</option>
                </select>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {set.isError && <ErrorNotice error={set.error} />}
    </div>
  );
}

export function NexrollAlongside({ state }: { state: AlongsideState }) {
  const { port } = state;
  return (
    <div className="stack">
      {port.restart_needed && (
        <Notice tone="warning" title="Restart needed">
          <p>
            Prerolls Max moves to port {port.configured} when it restarts. Then open{" "}
            <a href={addressWithPort(port.configured)}>{addressWithPort(port.configured)}</a>. Restart the Prerolls Max service (or the tray app) to
            switch now.
          </p>
        </Notice>
      )}
      {state.conflicts.map((c) => (
        <Notice key={c} tone="warning">
          {c}
        </Notice>
      ))}
      {state.summary && <p>{state.summary}</p>}
      <h4>1. Give Prerolls Max its own port</h4>
      <PortSetting state={state} />
      <h4>2. Pick who manages each server</h4>
      <p className="muted small">
        On a server left to NeXroll, Prerolls Max never writes Plex's intro list and its plugin adds nothing. Disconnect the other servers in NeXroll, and
        never let both apps manage one server: on Plex they take turns writing the list, and on Jellyfin or Emby with both plugins intros play twice.
      </p>
      <ServerTable state={state} />
    </div>
  );
}
