// Where trailers are kept, how many, and the TMDB key used to find them.
import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "../../../../lib/api";
import { cleanFolderPath, cleanToken } from "../../../../lib/validate";
import { TextField } from "../../../../components/Field";
import { SecretField } from "../../../../components/SecretField";
import { Select } from "../../../../components/Select";
import { Button } from "../../../../components/Button";
import { ErrorNotice, Notice } from "../../../../components/Notice";
import { useToast } from "../../../../components/Toast";
import { useSaveTrailerSettings, type TrailerSettings } from "./useTrailers";

type NumberField = "days_ahead" | "max_trailers" | "trailers_per_playback" | "trailer_retention_days";
const LIMITS: Record<NumberField, [number, number, string]> = {
  days_ahead: [7, 365, "Days ahead to look"],
  max_trailers: [1, 50, "Most trailers to keep"],
  trailers_per_playback: [1, 10, "Trailers before each movie"],
  trailer_retention_days: [0, 365, "Delete trailers after (days)"],
};

export function TrailerOptions({ settings }: { settings: TrailerSettings }) {
  const save = useSaveTrailerSettings();
  const toast = useToast();
  const [form, setForm] = useState({
    storage_path: settings.storage_path ?? "",
    quality: settings.quality || "1080",
    language: settings.trailer_language || "en",
    days_ahead: String(settings.days_ahead ?? 90),
    max_trailers: String(settings.max_trailers ?? 10),
    trailers_per_playback: String(settings.trailers_per_playback ?? 2),
    trailer_retention_days: String(settings.trailer_retention_days ?? 7),
  });
  const [errors, setErrors] = useState<Record<string, string | undefined>>({});
  useEffect(() => setForm((f) => ({ ...f, storage_path: settings.storage_path ?? f.storage_path })), [settings.storage_path]);

  const submit = () => {
    const next: Record<string, string | undefined> = {};
    const folder = form.storage_path.trim() ? cleanFolderPath(form.storage_path, { what: "trailer folder" }) : null;
    if (folder && !folder.ok) next.storage_path = folder.message;
    if (!form.storage_path.trim()) next.storage_path = "Enter the folder for trailers, or use the suggested one.";
    for (const [key, [min, max]] of Object.entries(LIMITS) as [NumberField, [number, number, string]][]) {
      const n = Number(form[key]);
      if (!Number.isInteger(n) || n < min || n > max) next[key] = `Use a whole number from ${min} to ${max}.`;
    }
    setErrors(next);
    if (Object.values(next).some(Boolean)) return;
    save.mutate(
      {
        storage_path: folder?.ok ? folder.value : undefined,
        quality: form.quality,
        trailer_language: form.language,
        days_ahead: Number(form.days_ahead),
        max_trailers: Number(form.max_trailers),
        trailers_per_playback: Number(form.trailers_per_playback),
        trailer_retention_days: Number(form.trailer_retention_days),
      },
      { onSuccess: () => toast({ tone: "success", title: "Trailer settings saved" }) },
    );
  };

  const languages = Array.isArray(settings.trailer_languages)
    ? (settings.trailer_languages as { code: string; label?: string; name?: string }[]).map((l) => ({ value: l.code, label: l.label ?? l.name ?? l.code }))
    : [{ value: "en", label: "English" }];

  return (
    <div className="stack">
      <TextField
        label="Folder for trailers"
        help={`Suggested: ${settings.recommended_storage_path}. Your media server must be able to see it.`}
        value={form.storage_path}
        error={errors.storage_path}
        onChange={(e) => setForm({ ...form, storage_path: e.target.value })}
      />
      {!settings.storage_path && (
        <div>
          <Button size="sm" onClick={() => setForm({ ...form, storage_path: settings.recommended_storage_path })}>
            Use the suggested folder
          </Button>
        </div>
      )}
      {settings.storage_path_needs_mapping_warning && (
        <Notice tone="warning">This folder is outside the intro folder. Add it to Folder mapping so your media server can find it.</Notice>
      )}
      <div className="form-grid">
        <Select
          label="Picture quality"
          value={form.quality}
          onChange={(quality) => setForm({ ...form, quality })}
          options={[
            { value: "720", label: "720p (smaller files)" },
            { value: "1080", label: "1080p" },
            { value: "4k", label: "4K (large files)" },
          ]}
        />
        <Select label="Trailer language" value={form.language} onChange={(language) => setForm({ ...form, language })} options={languages} />
        {(Object.keys(LIMITS) as NumberField[]).map((key) => (
          <TextField
            key={key}
            label={LIMITS[key][2]}
            type="number"
            inputMode="numeric"
            min={LIMITS[key][0]}
            max={LIMITS[key][1]}
            help={key === "trailer_retention_days" ? "0 keeps them until you delete them." : undefined}
            value={form[key]}
            error={errors[key]}
            onChange={(e) => setForm({ ...form, [key]: e.target.value })}
          />
        ))}
      </div>
      {save.isError && <ErrorNotice error={save.error} />}
      <div>
        <Button variant="primary" onClick={submit} loading={save.isPending}>
          Save trailer settings
        </Button>
      </div>
    </div>
  );
}

export function TmdbKey({ settings }: { settings: TrailerSettings }) {
  const save = useSaveTrailerSettings();
  const [key, setKey] = useState("");
  const [error, setError] = useState<string>();
  const test = useMutation({
    mutationFn: (value?: string) => api.get<{ valid: boolean; message: string; using_custom_key: boolean }>("/nexup/tmdb/test-key", { api_key: value }),
  });
  const check = () => {
    const r = cleanToken(key, { what: "TMDB key", minLen: 16 });
    setError(r.ok ? undefined : r.message);
    return r.ok ? r.value : null;
  };
  return (
    <div className="stack">
      <p className="muted">
        Prerolls Max looks up TV show trailers on The Movie Database (TMDB). The shared key it came with no longer works, so
        TV show trailers need a free key of your own: make one at themoviedb.org and paste it here. Movie trailers don&rsquo;t
        need it, because Radarr already knows each movie&rsquo;s trailer.
      </p>
      <p className="small">{settings.tmdb_api_key ? "Using your own key." : "No key of your own yet, so TV show trailers can't be looked up."}</p>
      <SecretField label="Your TMDB key" what="TMDB key" optional value={key} error={error} onChange={(e) => setKey(e.target.value)} />
      {test.data && <Notice tone={test.data.valid ? "success" : "error"}>{test.data.message}</Notice>}
      {(test.isError || save.isError) && <ErrorNotice error={test.error ?? save.error} />}
      <div className="form-actions">
        <Button
          onClick={() => {
            if (!key.trim()) return test.mutate(undefined);
            const value = check();
            if (value) test.mutate(value);
          }}
          loading={test.isPending}
        >
          Test
        </Button>
        <Button
          variant="primary"
          disabled={!key.trim()}
          loading={save.isPending}
          onClick={() => {
            const value = check();
            if (value) save.mutate({ tmdb_api_key: value }, { onSuccess: () => setKey("") });
          }}
        >
          Save key
        </Button>
      </div>
    </div>
  );
}
