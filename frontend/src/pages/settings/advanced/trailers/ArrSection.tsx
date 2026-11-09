// Radarr (movies) or Sonarr (TV): the main connection plus extra servers,
// such as a 4K one.
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Plus, Trash2 } from "lucide-react";
import { api } from "../../../../lib/api";
import { ApiError } from "../../../../lib/errors";
import { cleanApiKey, cleanName, cleanServerUrl } from "../../../../lib/validate";
import { TextField } from "../../../../components/Field";
import { SecretField } from "../../../../components/SecretField";
import { Button, IconButton } from "../../../../components/Button";
import { ErrorNotice, Notice } from "../../../../components/Notice";
import { useToast } from "../../../../components/Toast";
import { SETTINGS_KEY, useArrServers, type ArrKind, type ArrResult } from "./useTrailers";

const NAMES: Record<ArrKind, string> = { radarr: "Radarr", sonarr: "Sonarr" };
const PORTS: Record<ArrKind, number> = { radarr: 7878, sonarr: 8989 };

/** Turns {success: false, message} into an error the page can show. */
async function arrCall(call: Promise<ArrResult>): Promise<ArrResult> {
  const result = await call;
  if (!result.success) {
    throw new ApiError({ kind: "upstream", message: result.message || "That didn't connect.", hint: "Check the address and the API key, then try again." });
  }
  return result;
}

function ConnectForm({ kind, extra, onDone }: { kind: ArrKind; extra?: boolean; onDone: () => void }) {
  const name = NAMES[kind];
  const [values, setValues] = useState({ name: "", url: "", api_key: "" });
  const [errors, setErrors] = useState<Partial<Record<"name" | "url" | "api_key", string>>>({});
  const connect = useMutation({
    mutationFn: (body: Record<string, string>) =>
      arrCall(api.post<ArrResult>(extra ? `/nexup/${kind}/servers` : `/nexup/${kind}/connect`, body, { timeoutMs: 30_000 })),
    onSuccess: onDone,
  });
  const submit = () => {
    const url = cleanServerUrl(values.url, { service: name, defaultPort: PORTS[kind] });
    const key = cleanApiKey(values.api_key);
    const label = values.name.trim() ? cleanName(values.name, { what: "name", maxLen: 60 }) : null;
    const next = {
      url: url.ok ? undefined : url.message,
      api_key: key.ok ? undefined : key.message,
      name: label && !label.ok ? label.message : undefined,
    };
    setErrors(next);
    if (!url.ok || !key.ok || (label && !label.ok)) return;
    connect.mutate({ url: url.value, api_key: key.value, ...(label?.ok ? { name: label.value } : {}) });
  };
  return (
    <div className="stack">
      {extra && (
        <TextField label="Name" optional placeholder={`${name} 4K`} value={values.name} error={errors.name} onChange={(e) => setValues({ ...values, name: e.target.value })} />
      )}
      <div className="form-grid">
        <TextField
          label={`${name} address`}
          placeholder={`http://192.168.1.10:${PORTS[kind]}`}
          inputMode="url"
          autoCapitalize="none"
          help={`Port ${PORTS[kind]} is added if you leave it out.`}
          value={values.url}
          error={errors.url}
          onChange={(e) => setValues({ ...values, url: e.target.value })}
        />
        <SecretField
          label="API key"
          what={`${name} API key`}
          help={`In ${name}: Settings, then General, then API Key.`}
          value={values.api_key}
          error={errors.api_key}
          onChange={(e) => setValues({ ...values, api_key: e.target.value })}
        />
      </div>
      {connect.isError && <ErrorNotice error={connect.error} />}
      <div>
        <Button variant="primary" onClick={submit} loading={connect.isPending}>
          {extra ? `Add this ${name}` : `Connect ${name}`}
        </Button>
      </div>
    </div>
  );
}

export function ArrSection({ kind, connected, url }: { kind: ArrKind; connected: boolean; url: string | null }) {
  const name = NAMES[kind];
  const queryClient = useQueryClient();
  const toast = useToast();
  const [adding, setAdding] = useState(false);
  const servers = useArrServers(kind, connected);
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: SETTINGS_KEY });
    void queryClient.invalidateQueries({ queryKey: ["arr-servers", kind] });
    void queryClient.invalidateQueries({ queryKey: ["upcoming"] });
  };
  const disconnect = useMutation({
    mutationFn: () => api.del(`/nexup/${kind}/disconnect`),
    onSuccess: () => {
      refresh();
      toast({ tone: "success", title: `Disconnected ${name}` });
    },
  });
  const test = useMutation({
    mutationFn: (id: number) => arrCall(api.post<ArrResult>(`/nexup/${kind}/servers/${id}/test`, {}, { timeoutMs: 30_000 })),
    onSuccess: (r) => toast({ tone: "success", title: r.message ?? "Connected" }),
    onError: (e) => toast({ tone: "error", title: e instanceof Error ? e.message : "That didn't connect." }),
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.del(`/nexup/${kind}/servers/${id}`),
    onSuccess: refresh,
  });

  if (!connected) {
    return <ConnectForm kind={kind} onDone={refresh} />;
  }
  return (
    <div className="stack">
      <div className="row">
        <CheckCircle2 size={20} className="status-ok" aria-hidden="true" />
        <span className="grow">
          Connected to <strong>{url}</strong>
        </span>
        <Button size="sm" variant="ghost" loading={disconnect.isPending} onClick={() => disconnect.mutate()}>
          Disconnect
        </Button>
      </div>
      {servers.data && servers.data.length > 0 && (
        <ul className="list">
          {servers.data.map((s) => (
            <li key={s.id} className="list-row">
              <div className="grow">
                <strong>{s.name}</strong>
                <div className="muted small">{s.url}</div>
              </div>
              <Button size="sm" loading={test.isPending && test.variables === s.id} onClick={() => test.mutate(s.id)}>
                Test
              </Button>
              <IconButton label={`Remove ${s.name}`} onClick={() => remove.mutate(s.id)}>
                <Trash2 size={18} aria-hidden="true" />
              </IconButton>
            </li>
          ))}
        </ul>
      )}
      {remove.isError && <ErrorNotice error={remove.error} />}
      {adding ? (
        <Notice tone="info" title={`Another ${name}`}>
          <p>For example a second {name} for 4K. Movies and shows on both are only counted once.</p>
          <ConnectForm
            kind={kind}
            extra
            onDone={() => {
              setAdding(false);
              refresh();
            }}
          />
        </Notice>
      ) : (
        <div>
          <Button size="sm" icon={<Plus size={16} aria-hidden="true" />} onClick={() => setAdding(true)}>
            Add another {name}
          </Button>
        </div>
      )}
    </div>
  );
}
