// Jellyfin and Emby ask the Prerolls Max Intros plugin which intro to play.
// Four steps: download it, put it in the server's plugins folder, let
// Prerolls Max fill in its settings, then check it has asked for intros.
// With `server`, every step acts on that one server (/api/servers/{id}/plugin);
// each server's plugin gets its own key.
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { api } from "../../lib/api";
import { errorFromResponse, NETWORK_ERROR } from "../../lib/errors";
import { cleanServerUrl } from "../../lib/validate";
import { SERVER_NAMES, useCapabilities } from "../../lib/capabilities";
import type { MediaServer } from "../../lib/mediaServers";
import { TextField } from "../../components/Field";
import { Button } from "../../components/Button";
import { ErrorNotice, Notice } from "../../components/Notice";
import { ConnectionSteps } from "./ConnectionSteps";
import { ServerTestSteps } from "./ServerTestSteps";

type PluginServer = "jellyfin" | "emby";

interface Detect {
  detected?: boolean;
  plugin?: { name: string; version: string; status: string };
  config?: Record<string, unknown>;
  suggested_nexroll_url?: string;
  auth_error?: boolean;
}

const FOLDERS: Record<PluginServer, { what: string; where: string[] }> = {
  jellyfin: {
    what: "Unzip the file into a new folder called PrerollsMax inside Jellyfin's plugins folder.",
    where: [
      "Docker: /config/plugins (inside the folder you mapped to /config)",
      "Linux: /var/lib/jellyfin/plugins",
      "Windows: %LOCALAPPDATA%\\jellyfin\\plugins",
    ],
  },
  emby: {
    what: "Copy PrerollsMax.Emby.dll into Emby's plugins folder. Don't put it in a subfolder.",
    where: [
      "Docker: /config/plugins (inside the folder you mapped to /config)",
      "Linux: /var/lib/emby/plugins",
      "Windows: %APPDATA%\\Emby-Server\\programdata\\plugins",
    ],
  },
};

/** Fetches the file first, so a missing plugin shows a message instead of a broken download. */
async function downloadPlugin(type: PluginServer, serverId?: number): Promise<string> {
  let response: Response;
  try {
    response = await fetch(`/${type}/plugin/download${serverId ? `?server_id=${serverId}` : ""}`, { credentials: "same-origin" });
  } catch {
    throw NETWORK_ERROR();
  }
  if (!response.ok) {
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      body = undefined;
    }
    throw errorFromResponse(response.status, body, response.headers.get("x-request-id"));
  }
  const blob = await response.blob();
  const match = /filename="?([^";]+)"?/i.exec(response.headers.get("content-disposition") ?? "");
  const name = match?.[1] ?? (type === "emby" ? "PrerollsMax.Emby.dll" : "PrerollsMax.Jellyfin.zip");
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
  return name;
}

export function PluginSetup({ type, server }: { type: PluginServer; server?: Pick<MediaServer, "id" | "name"> }) {
  const name = server?.name ?? SERVER_NAMES[type];
  const kind = SERVER_NAMES[type];
  const queryClient = useQueryClient();
  const caps = useCapabilities();
  const typeCaps = caps.data?.servers.find((s) => s.type === type);
  const plugin = server ? typeCaps?.instances?.find((i) => i.id === server.id)?.plugin : typeCaps?.plugin;
  const pluginPath = server ? `/api/servers/${server.id}/plugin` : `/${type}/plugin/detect`;
  const detectKey = ["plugin-detect", type, server?.id ?? 0];
  const detect = useQuery({
    queryKey: detectKey,
    queryFn: () => api.get<Detect>(pluginPath, undefined, { timeoutMs: 20_000 }),
    retry: false,
  });
  const [address, setAddress] = useState(window.location.origin);
  const [addressError, setAddressError] = useState<string>();
  const [testRun, setTestRun] = useState(0);

  const download = useMutation({ mutationFn: () => downloadPlugin(type, server?.id) });
  const configure = useMutation({
    mutationFn: (url: string) =>
      api.post<{ reach?: { ok: boolean; message: string } | null }>(
        server ? `/api/servers/${server.id}/plugin` : `/${type}/plugin/configure`,
        { nexroll_url: url },
        { timeoutMs: 45_000 },
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: detectKey });
      await queryClient.invalidateQueries({ queryKey: ["capabilities"] });
      await queryClient.invalidateQueries({ queryKey: ["media-servers"] });
    },
  });

  const installed = Boolean(detect.data?.detected);
  // The server asks the plugin to call Prerolls Max back: saved but unreachable isn't done.
  const unreachable = configure.data?.reach?.ok === false ? configure.data.reach : undefined;
  const configured =
    !unreachable && (configure.isSuccess || Boolean(detect.data?.config && detect.data.config.ApiKey === "set"));
  const checkedIn = Boolean(plugin?.connected);

  const submit = () => {
    const check = cleanServerUrl(address, { service: "Prerolls Max" });
    if (!check.ok) {
      setAddressError(check.message);
      return;
    }
    setAddressError(undefined);
    configure.mutate(check.value);
  };

  const folders = FOLDERS[type];
  return (
    <div className="stack">
      <p className="muted">
        {name} doesn't know about Prerolls Max on its own. A small plugin asks Prerolls Max which intro to play each time
        something starts.
      </p>
      <ol className="setup-steps">
        <li className={`setup-step ${download.isSuccess || installed ? "done" : ""}`}>
          <div>
            <h4>Download the plugin</h4>
            <Button size="sm" icon={<Download size={16} aria-hidden="true" />} loading={download.isPending} onClick={() => download.mutate()}>
              Download the plugin for {kind}
            </Button>
            {download.isSuccess && <p className="small muted">Saved as {download.data}.</p>}
            {download.isError && <ErrorNotice error={download.error} />}
          </div>
        </li>
        <li className={`setup-step ${installed ? "done" : ""}`}>
          <div>
            <h4>Put it in {name}'s plugins folder, then restart {name}</h4>
            <p>{folders.what}</p>
            <ul className="small muted">
              {folders.where.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
            {installed ? (
              <Notice tone="success">
                {name} has the plugin{detect.data?.plugin?.version ? ` (version ${detect.data.plugin.version})` : ""}.
              </Notice>
            ) : (
              <Button size="sm" loading={detect.isFetching} onClick={() => detect.refetch()}>
                I've restarted {name}
              </Button>
            )}
            {detect.data && !installed && !detect.isFetching && detect.dataUpdatedAt > 0 && (
              <p className="small muted">
                {detect.data.auth_error
                  ? `${name} won't list its plugins for this API key. Use a key made by an administrator.`
                  : `${name} doesn't show the plugin yet. Check the folder, and that ${name} restarted.`}
              </p>
            )}
            {detect.isError && <ErrorNotice error={detect.error} />}
          </div>
        </li>
        <li className={`setup-step ${configured ? "done" : ""}`}>
          <div>
            <h4>Let Prerolls Max fill in the plugin's settings</h4>
            <TextField
              label={`Address ${name} uses to reach Prerolls Max`}
              help={`Usually right as it is. If ${name} runs on another computer or in Docker, use this computer's IP address instead of "localhost".`}
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              error={addressError}
              inputMode="url"
              autoCapitalize="none"
            />
            {configure.isSuccess && !unreachable && (
              <Notice tone="success">Done. The plugin knows where Prerolls Max is and has its own key.</Notice>
            )}
            {unreachable && (
              <Notice tone="warning" title={`Saved, but ${name} can't reach Prerolls Max at this address`}>
                {unreachable.message || "Check the address."} Change the address above, then press the button again.
              </Notice>
            )}
            {configure.isError && <ErrorNotice error={configure.error} />}
            <div className="notice-action">
              <Button onClick={submit} loading={configure.isPending} variant={configured ? "secondary" : "primary"}>
                Set up the plugin for me
              </Button>
            </div>
          </div>
        </li>
        <li className={`setup-step ${checkedIn ? "done" : ""}`}>
          <div>
            <h4>Play something to check</h4>
            <p>Start any movie in {name}. The plugin asks for an intro, and the check below turns green.</p>
            {plugin && <p className="small muted">{checkedIn ? `The plugin${plugin.version ? ` ${plugin.version}` : ""} has asked for intros.` : plugin.note}</p>}
            <Button size="sm" onClick={() => setTestRun((n) => n + 1)}>
              Check now
            </Button>
            {testRun > 0 &&
              (server ? <ServerTestSteps server={server} run={testRun} /> : <ConnectionSteps type={type} autoRun={testRun} button={false} />)}
          </div>
        </li>
      </ol>
    </div>
  );
}
