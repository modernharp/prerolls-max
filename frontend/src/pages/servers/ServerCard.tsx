// One media server on the Media Servers page: its name, address and status,
// Test connection, plugin setup (Jellyfin, Emby), folder mapping (Plex),
// Play a test, Edit, Switch off and Disconnect.
import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Circle, PauseCircle } from "lucide-react";
import { api } from "../../lib/api";
import { useCapabilities, type PluginState } from "../../lib/capabilities";
import type { MediaServer } from "../../lib/mediaServers";
import { Button } from "../../components/Button";
import { ConfirmDialog, Modal } from "../../components/Dialog";
import { ErrorNotice, Notice } from "../../components/Notice";
import { ServerPlayTest } from "../../components/ServerPlayTest";
import { useToast } from "../../components/Toast";
import { PluginSetup } from "./PluginSetup";
import { ServerTestSteps } from "./ServerTestSteps";
import { ServerManagerSwitch } from "./ServerManagerSwitch";

function StatusBadge({ server }: { server: MediaServer }) {
  if (!server.enabled) {
    return (
      <span className="badge">
        <PauseCircle size={14} aria-hidden="true" /> Switched off
      </span>
    );
  }
  if (!server.status) {
    return (
      <span className="badge">
        <Circle size={14} aria-hidden="true" /> Checking…
      </span>
    );
  }
  return server.status.connected ? (
    <span className="badge badge-success">
      <CheckCircle2 size={14} aria-hidden="true" /> Connected
    </span>
  ) : (
    <span className="badge badge-danger">
      <AlertTriangle size={14} aria-hidden="true" /> Problem
    </span>
  );
}

/**
 * The plugin on one Jellyfin or Emby card. A working plugin is one line
 * ("Prerolls Max plugin · Working · version 2.1.0.0 · Show setup steps");
 * the four setup steps open by themselves only when it needs attention.
 */
export function PluginSection({ server, plugin, loaded }: { server: MediaServer; plugin?: PluginState; loaded: boolean }) {
  const [userOpen, setUserOpen] = useState<boolean | null>(null);
  const working = Boolean(plugin?.connected);
  const needsAttention = server.enabled && loaded && !working;
  const open = userOpen ?? needsAttention;
  const stepsId = `plugin-steps-${server.id}`;
  return (
    <div className="plugin-section">
      <p className="plugin-line small">
        {/* Each item after the first brings its own "·" (CSS), so a wrapped line never ends in one. */}
        <strong className="plugin-line-item">Prerolls Max plugin</strong>
        <span className="plugin-line-item">
          {working ? <span className="badge badge-success">Working</span> : <span className="badge badge-warning">Needs setting up</span>}
        </span>
        {working && plugin?.version && <span className="plugin-line-item muted">version {plugin.version}</span>}
        <span className="plugin-line-item">
          <button type="button" className="btn-link" aria-expanded={open} aria-controls={stepsId} onClick={() => setUserOpen(!open)}>
            {open ? "Hide setup steps" : "Show setup steps"}
          </button>
        </span>
      </p>
      {open && (
        <div id={stepsId}>
          <PluginSetup type={server.type as "jellyfin" | "emby"} server={server} />
        </div>
      )}
    </div>
  );
}

export function ServerCard({ server, onEdit }: { server: MediaServer; onEdit: () => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const caps = useCapabilities();
  const [testRun, setTestRun] = useState(0);
  const [confirm, setConfirm] = useState(false);
  const [playTest, setPlayTest] = useState(false);
  const plugin = caps.data?.servers.find((s) => s.type === server.type)?.instances?.find((i) => i.id === server.id)?.plugin;
  const headingId = `server-${server.id}`;

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["media-servers"] });
    await queryClient.invalidateQueries({ queryKey: ["capabilities"] });
    for (const t of ["plex", "jellyfin", "emby"]) await queryClient.invalidateQueries({ queryKey: ["server-status", t] });
  };
  const toggle = useMutation({
    mutationFn: () => api.put<MediaServer>(`/api/servers/${server.id}`, { enabled: !server.enabled }),
    onSuccess: async (saved) => {
      await refresh();
      toast({ tone: "success", title: saved.enabled ? `${saved.name} is switched on` : `${saved.name} is switched off` });
    },
  });
  const remove = useMutation({
    mutationFn: () => api.del(`/api/servers/${server.id}`),
    onSuccess: async () => {
      await refresh();
      toast({ tone: "success", title: `Disconnected ${server.name}` });
    },
  });

  const problem = server.enabled && server.status && !server.status.connected ? server.status : null;
  const apply = server.last_apply;
  return (
    <article className={`card server-card ${server.enabled ? "" : "off"}`} aria-labelledby={headingId}>
      <div className="row-between">
        <h3 id={headingId}>{server.name}</h3>
        <StatusBadge server={server} />
      </div>
      <p className="muted small server-url">
        {server.type_label} at {server.url}
        {server.status?.version ? ` · version ${server.status.version}` : ""}
      </p>
      {problem && (
        <Notice tone="error" title={problem.message ?? `Prerolls Max can't reach ${server.name}.`}>
          {problem.hint}
        </Notice>
      )}
      {server.enabled && apply && apply.state !== "ok" && (
        <Notice tone={apply.state === "waiting" ? "info" : "warning"} title={apply.state === "waiting" ? "Waiting for playback to finish" : "The last change didn't reach it"}>
          {apply.message}
        </Notice>
      )}
      {server.enabled && apply?.state === "ok" && apply.message && <Notice tone="warning">{apply.message}</Notice>}

      <div className="form-actions">
        <Button onClick={() => setTestRun((n) => n + 1)}>Test connection</Button>
        <Button onClick={() => setPlayTest(true)} disabled={!server.enabled}>Play a test</Button>
        <Button variant="ghost" onClick={onEdit}>Edit</Button>
        <Button variant="ghost" loading={toggle.isPending} onClick={() => toggle.mutate()}>
          {server.enabled ? "Switch off" : "Switch on"}
        </Button>
        <Button variant="danger-outline" onClick={() => setConfirm(true)}>Disconnect</Button>
      </div>
      {toggle.isError && <ErrorNotice error={toggle.error} />}
      <ServerManagerSwitch server={server} />
      {testRun > 0 && <ServerTestSteps server={server} run={testRun} />}

      {server.type === "plex" ? (
        <p className="small">
          Folder mapping:{" "}
          {server.mappings?.length
            ? server.mappings.map((m) => `${m.local} → ${m.plex}`).join(", ")
            : "none (paths are sent as they are)"}{" "}
          <Link to={`/settings/advanced/folder-mapping?server=${server.id}`}>Change</Link>
        </p>
      ) : (
        <PluginSection server={server} plugin={plugin} loaded={!caps.isLoading} />
      )}

      <Modal open={playTest} onOpenChange={setPlayTest} title={`Play a test on ${server.name}`} wide
        description="Prerolls Max asks the server what it would play before a movie. Nothing starts playing.">
        {playTest && <ServerPlayTest serverId={server.id} />}
      </Modal>
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title={`Disconnect ${server.name}?`}
        body={
          <p>
            Prerolls Max forgets this server and stops looking after its intros
            {server.type === "plex" ? "" : "; its plugin's key stops working"}. Your videos and schedules stay. You can add it
            again any time.
          </p>
        }
        confirmLabel="Disconnect"
        danger
        onConfirm={() => remove.mutateAsync()}
      />
    </article>
  );
}
