// Jellyfin and Emby: address plus an API key made in the server's dashboard.
// With `add`, it adds another server to the list (POST /api/servers).
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { keys } from "../../lib/queries";
import { zChecked } from "../../lib/schemas";
import { cleanApiKey, cleanServerUrl } from "../../lib/validate";
import { SERVER_NAMES } from "../../lib/capabilities";
import { TextField, applyServerFields } from "../../components/Field";
import { SecretField } from "../../components/SecretField";
import { Button } from "../../components/Button";
import { ErrorNotice } from "../../components/Notice";
import type { AddMode } from "./PlexConnect";

export function KeyConnect({ type, onConnected, add }: { type: "jellyfin" | "emby"; onConnected: () => void; add?: AddMode }) {
  const name = SERVER_NAMES[type];
  const schema = z.object({
    url: zChecked((v) => cleanServerUrl(v, { service: name, defaultPort: 8096 })),
    api_key: zChecked(cleanApiKey),
  });
  type Input = z.input<typeof schema>;
  type Output = z.output<typeof schema>;
  const queryClient = useQueryClient();
  const { register, handleSubmit, setError, formState: { errors } } = useForm<Input, unknown, Output>({
    resolver: zodResolver(schema),
    mode: "onTouched",
  });
  const connect = useMutation({
    mutationFn: (v: Output & { name?: string }) =>
      add
        ? api.post("/api/servers", { type, name: v.name, url: v.url, token: v.api_key }, { timeoutMs: 30_000 })
        : api.post(`/${type}/connect`, v, { timeoutMs: 30_000 }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: keys.server(type) });
      await queryClient.invalidateQueries({ queryKey: ["capabilities"] });
      await queryClient.invalidateQueries({ queryKey: ["media-servers"] });
      onConnected();
    },
    onError: (error) =>
      applyServerFields(error, (name, e) => setError((name === ("token" as never) ? "api_key" : name) as never, e), ["url", "api_key", "token"], [
        [/api key|turned down|unauthori|forbidden/i, "api_key"],
        [/answer|reach|address|url|connect/i, "url"],
      ]),
  });

  return (
    <section className="card stack" aria-labelledby="key-connect">
      <h2 id="key-connect">{add ? `Add a ${name} server` : `Connect ${name}`}</h2>
      <ol className="numbered">
        <li>Open {name} in your browser and sign in as an administrator.</li>
        <li>
          {type === "emby"
            ? 'Go to Settings, then API Keys, and add a key called "Prerolls Max".'
            : 'Go to Dashboard, then API Keys, and add a key called "Prerolls Max".'}
        </li>
        <li>Copy the key and paste it below.</li>
      </ol>
      <form
        className="stack"
        onSubmit={handleSubmit((v) => {
          const name = add ? add.getName() : undefined;
          if (name !== null) connect.mutate(add ? { ...v, name } : v);
        }, () => add?.getName())}
        noValidate
      >
        <TextField
          label={`${name} address`}
          placeholder="http://192.168.1.10:8096"
          inputMode="url"
          autoCapitalize="none"
          help="The address you use to open it in a browser. Port 8096 is added if you leave it out."
          error={errors.url?.message}
          {...register("url")}
        />
        <SecretField label="API key" error={errors.api_key?.message} {...register("api_key")} />
        {connect.isError && !Object.keys(errors).length && <ErrorNotice error={connect.error} />}
        <div>
          <Button type="submit" variant="primary" loading={connect.isPending}>
            Connect
          </Button>
        </div>
      </form>
    </section>
  );
}
