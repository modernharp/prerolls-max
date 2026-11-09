// Plex: "Sign in with Plex" first; address + token under "Other ways".
// With `add`, both add another Plex server to the list (POST /api/servers)
// instead of replacing the first one.
import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { api } from "../../lib/api";
import { keys } from "../../lib/queries";
import { zChecked } from "../../lib/schemas";
import { cleanServerUrl, cleanToken } from "../../lib/validate";
import { TextField, applyServerFields } from "../../components/Field";
import { SecretField } from "../../components/SecretField";
import { Button } from "../../components/Button";
import { ErrorNotice, Notice } from "../../components/Notice";
import { HelpButton } from "../../components/HelpPanel";

type Phase = "idle" | "waiting" | "finishing" | "expired";

/** Adding a server: the name it gets (null when the name field has a problem). */
export interface AddMode {
  getName: () => string | null;
}

function SignInWithPlex({ onConnected, add }: { onConnected: () => void; add?: AddMode }) {
  const queryClient = useQueryClient();
  const [phase, setPhase] = useState<Phase>("idle");
  const [link, setLink] = useState<string>();
  const [error, setError] = useState<unknown>(null);
  const timer = useRef<number>(undefined);

  useEffect(() => () => window.clearInterval(timer.current), []);

  const start = async () => {
    setError(null);
    const name = add ? add.getName() : undefined;
    if (name === null) return;
    setPhase("waiting");
    try {
      const { id, url } = await api.post<{ id: string; url: string }>("/plex/tv/start", {}, { timeoutMs: 30_000 });
      setLink(url);
      window.open(url, "plex-sign-in", "width=600,height=750");
      const started = Date.now();
      timer.current = window.setInterval(async () => {
        if (Date.now() - started > 10 * 60_000) {
          window.clearInterval(timer.current);
          setPhase("expired");
          return;
        }
        try {
          const s = await api.get<{ status: string }>(`/plex/tv/status/${id}`);
          if (s.status === "pending") return;
          window.clearInterval(timer.current);
          if (s.status !== "success") {
            setPhase("expired");
            return;
          }
          setPhase("finishing");
          await api.post(
            "/plex/tv/connect",
            add ? { id, prefer_local: true, add_server: true, name } : { id, prefer_local: true, save_token: true },
            { timeoutMs: 60_000 },
          );
          await queryClient.invalidateQueries({ queryKey: keys.server("plex") });
          await queryClient.invalidateQueries({ queryKey: ["media-servers"] });
          setPhase("idle");
          onConnected();
        } catch (e) {
          window.clearInterval(timer.current);
          setError(e);
          setPhase("idle");
        }
      }, 2000);
    } catch (e) {
      setError(e);
      setPhase("idle");
    }
  };

  return (
    <section className="card stack" aria-labelledby="plex-signin">
      <h2 id="plex-signin">Sign in with Plex</h2>
      <p className="muted">
        A Plex window opens. Sign in there and Prerolls Max finds your server by itself. Your Plex password never comes
        here.
      </p>
      {phase === "waiting" && (
        <Notice tone="info" title="Waiting for you to sign in to Plex…">
          {link && (
            <p>
              No window? <a href={link} target="_blank" rel="noreferrer noopener">Open the Plex sign-in page <ExternalLink size={14} aria-hidden="true" /></a>
            </p>
          )}
        </Notice>
      )}
      {phase === "finishing" && <Notice tone="info">Signed in. Finding your Plex server…</Notice>}
      {phase === "expired" && <Notice tone="warning" title="The sign-in timed out">Start again and finish signing in within 10 minutes.</Notice>}
      {error ? <ErrorNotice error={error} /> : null}
      <div>
        <Button variant="primary" onClick={start} loading={phase === "waiting" || phase === "finishing"}>
          Sign in with Plex
        </Button>
      </div>
    </section>
  );
}

const manualSchema = z.object({
  url: zChecked((v) => cleanServerUrl(v, { service: "Plex", defaultPort: 32400 })),
  token: zChecked((v) => cleanToken(v, { what: "token" })),
});
type ManualInput = z.input<typeof manualSchema>;
type ManualOutput = z.output<typeof manualSchema>;

function ManualPlex({ onConnected, add }: { onConnected: () => void; add?: AddMode }) {
  const queryClient = useQueryClient();
  const { register, handleSubmit, setError, formState: { errors } } = useForm<ManualInput, unknown, ManualOutput>({
    resolver: zodResolver(manualSchema),
    mode: "onTouched",
  });
  const connect = useMutation({
    mutationFn: (v: ManualOutput & { name?: string }) =>
      add
        ? api.post("/api/servers", { type: "plex", ...v }, { timeoutMs: 30_000 })
        : api.post("/plex/connect", v, { timeoutMs: 30_000 }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: keys.server("plex") });
      await queryClient.invalidateQueries({ queryKey: ["media-servers"] });
      onConnected();
    },
    onError: (error) =>
      applyServerFields(error, setError, ["url", "token"], [
        [/token|turned down|unauthori/i, "token"],
        [/answer|reach|address|url|connect/i, "url"],
      ]),
  });
  return (
    <form
      className="stack"
      onSubmit={handleSubmit((v) => {
        const name = add ? add.getName() : undefined;
        if (name !== null) connect.mutate(add ? { ...v, name } : v);
      }, () => add?.getName())}
      noValidate
    >
      <TextField
        label="Plex address"
        placeholder="http://192.168.1.10:32400"
        inputMode="url"
        autoCapitalize="none"
        help="The address of the computer running Plex. Port 32400 is added if you leave it out."
        error={errors.url?.message}
        {...register("url")}
      />
      <SecretField
        label="Plex token"
        help={
          <>
            A long code that lets Prerolls Max talk to Plex. <HelpButton slug="connect-plex" label="How to find your Plex token" />
          </>
        }
        error={errors.token?.message}
        {...register("token")}
      />
      {connect.isError && !Object.keys(errors).length && <ErrorNotice error={connect.error} />}
      <div>
        <Button type="submit" variant="primary" loading={connect.isPending}>
          Connect
        </Button>
      </div>
    </form>
  );
}

export function PlexConnect({ onConnected, add }: { onConnected: () => void; add?: AddMode }) {
  return (
    <>
      <SignInWithPlex onConnected={onConnected} add={add} />
      <details className="card details-card">
        <summary>
          <strong>Other ways to connect</strong>
          <span className="muted small"> Type the address and paste a token</span>
        </summary>
        <ManualPlex onConnected={onConnected} add={add} />
      </details>
    </>
  );
}
