// "Add a server" (pick the type, name it, then the usual connect form) and
// "Edit" (name, address, key) for one server on the Media Servers page.
import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { api } from "../../lib/api";
import { isApiError } from "../../lib/errors";
import { SERVER_NAMES, type ServerType } from "../../lib/capabilities";
import { nameTaken, suggestName, type MediaServer } from "../../lib/mediaServers";
import { cleanApiKey, cleanName, cleanServerUrl, cleanToken } from "../../lib/validate";
import { Modal } from "../../components/Dialog";
import { TextField } from "../../components/Field";
import { SecretField } from "../../components/SecretField";
import { Button } from "../../components/Button";
import { ErrorNotice } from "../../components/Notice";
import { useToast } from "../../components/Toast";
import { PlexConnect, type AddMode } from "./PlexConnect";
import { KeyConnect } from "./KeyConnect";

const TYPES: { type: ServerType; text: string }[] = [
  { type: "plex", text: "Plex Media Server. Prerolls Max writes the intro list into its settings." },
  { type: "jellyfin", text: "Jellyfin 10.11 or 12, with the Prerolls Max Intros plugin." },
  { type: "emby", text: "Emby Server 4.9 or newer, with the Prerolls Max Intros plugin." },
];

/** The name check used by both dialogs: plain words, same rules as the server. */
function checkName(value: string, servers: MediaServer[], exceptId?: number): { ok: true; value: string } | { ok: false; message: string } {
  const check = cleanName(value, { what: "server name", maxLen: 60 });
  if (!check.ok) return check;
  if (nameTaken(check.value, servers, exceptId)) return { ok: false, message: `There's already a media server called "${check.value}".` };
  return check;
}

export function AddServerDialog({ open, onOpenChange, servers }: { open: boolean; onOpenChange: (open: boolean) => void; servers: MediaServer[] }) {
  const [type, setType] = useState<ServerType | null>(null);
  const [name, setName] = useState("");
  const [nameError, setNameError] = useState<string>();
  const toast = useToast();

  const close = (next: boolean) => {
    onOpenChange(next);
    if (!next) {
      setType(null);
      setNameError(undefined);
    }
  };
  const pick = (t: ServerType) => {
    setType(t);
    setName(suggestName(servers, SERVER_NAMES[t]));
    setNameError(undefined);
  };
  const add: AddMode = {
    getName: () => {
      const check = checkName(name, servers);
      setNameError(check.ok ? undefined : check.message);
      return check.ok ? check.value : null;
    },
  };
  const done = () => {
    toast({ tone: "success", title: `Added ${name.trim()}`, description: type === "plex" ? undefined : "Next, set up its plugin on its card." });
    close(false);
  };

  return (
    <Modal open={open} onOpenChange={close} title={type ? `Add a ${SERVER_NAMES[type]} server` : "Add a server"} wide
      description={type ? undefined : "Which kind of media server is it?"}>
      {!type ? (
        <ul className="choice-grid plain-list">
          {TYPES.map((t) => (
            <li key={t.type}>
              <button type="button" className="choice choice-button" onClick={() => pick(t.type)}>
                <span className="choice-title">{SERVER_NAMES[t.type]}</span>
                <span className="small muted">{t.text}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <div className="stack">
          <div>
            <Button size="sm" variant="ghost" icon={<ArrowLeft size={16} aria-hidden="true" />} onClick={() => setType(null)}>
              Another kind of server
            </Button>
          </div>
          <TextField
            label="Name"
            help="Shown wherever Prerolls Max talks about this server, like &quot;Living room&quot;."
            value={name}
            maxLength={80}
            onChange={(e) => {
              setName(e.target.value);
              setNameError(undefined);
            }}
            onBlur={() => add.getName()}
            error={nameError}
          />
          {type === "plex" ? <PlexConnect add={add} onConnected={done} /> : <KeyConnect type={type} add={add} onConnected={done} />}
        </div>
      )}
    </Modal>
  );
}

type Fields = { name?: string; url?: string; token?: string };

export function EditServerDialog({ server, servers, onClose }: { server: MediaServer | null; servers: MediaServer[]; onClose: () => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [name, setName] = useState(server?.name ?? "");
  const [url, setUrl] = useState(server?.url ?? "");
  const [token, setToken] = useState("");
  const [errors, setErrors] = useState<Fields>({});
  const save = useMutation({
    mutationFn: (body: Fields) => api.put<MediaServer>(`/api/servers/${server?.id}`, body, { timeoutMs: 30_000 }),
    onSuccess: async (saved) => {
      await queryClient.invalidateQueries({ queryKey: ["media-servers"] });
      await queryClient.invalidateQueries({ queryKey: ["capabilities"] });
      toast({ tone: "success", title: `Saved ${saved.name}` });
      onClose();
    },
    onError: (error) => {
      if (isApiError(error) && Object.keys(error.fields).length) setErrors(error.fields as Fields);
    },
  });
  if (!server) return null;
  const keyWord = server.type === "plex" ? "token" : "API key";

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const next: Fields = {};
    const n = checkName(name, servers, server.id);
    if (!n.ok) next.name = n.message;
    const u = cleanServerUrl(url, { service: server.type_label, defaultPort: server.type === "plex" ? 32400 : 8096 });
    if (!u.ok) next.url = u.message;
    const t = token.trim() ? (server.type === "plex" ? cleanToken(token, { what: "token" }) : cleanApiKey(token)) : null;
    if (t && !t.ok) next.token = t.message;
    setErrors(next);
    if (Object.keys(next).length || !n.ok || !u.ok) return;
    const body: Fields = {};
    if (n.value !== server.name) body.name = n.value;
    if (u.value !== server.url) body.url = u.value;
    if (t?.ok) body.token = t.value;
    if (!Object.keys(body).length) return onClose();
    save.mutate(body);
  };
  const hasFieldErrors = isApiError(save.error) && Object.keys(save.error.fields).length > 0;

  return (
    <Modal open onOpenChange={(o) => !o && onClose()} title={`Edit ${server.name}`}>
      <form className="stack" onSubmit={submit} noValidate>
        <TextField label="Name" value={name} maxLength={80} onChange={(e) => setName(e.target.value)} error={errors.name} />
        <TextField label={`${server.type_label} address`} value={url} inputMode="url" autoCapitalize="none"
          onChange={(e) => setUrl(e.target.value)} error={errors.url}
          help="Prerolls Max checks that the server answers before saving a new address." />
        <SecretField label={server.type === "plex" ? "Plex token" : "API key"} value={token}
          onChange={(e) => setToken(e.target.value)} error={errors.token} optional
          help={`Leave it empty to keep the ${keyWord} Prerolls Max has.`} />
        {save.isError && !hasFieldErrors && <ErrorNotice error={save.error} />}
        <div className="form-actions">
          <Button type="submit" variant="primary" loading={save.isPending}>Save</Button>
          <Button onClick={onClose}>Cancel</Button>
        </div>
      </form>
    </Modal>
  );
}
