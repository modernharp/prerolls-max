// Folder mapping: when Prerolls Max and the media server see the same
// folder under different paths (usually because of Docker). Each Plex
// server has its own (?server=<id>); without one, the first Plex server's.
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, FolderSearch, Plus, Trash2 } from "lucide-react";
import { api } from "../../../lib/api";
import { cleanFolderPath } from "../../../lib/validate";
import type { PathMapping } from "../../../lib/types";
import { useMediaServers } from "../../../lib/mediaServers";
import { TextField } from "../../../components/Field";
import { Select } from "../../../components/Select";
import { Button, IconButton } from "../../../components/Button";
import { ErrorNotice, Loading, Notice } from "../../../components/Notice";
import { useToast } from "../../../components/Toast";

type RowErrors = { local?: string; plex?: string };

function Example() {
  return (
    <figure className="mapping-example" aria-label="Example">
      <div className="mapping-box">
        <span className="small muted">Prerolls Max sees the folder as</span>
        <code>/data/prerolls</code>
      </div>
      <ArrowRight size={24} aria-hidden="true" className="mapping-arrow" />
      <div className="mapping-box">
        <span className="small muted">Plex sees the same folder as</span>
        <code>/media/prerolls</code>
      </div>
      <figcaption className="muted small">
        Both are the same folder on your computer, for example <code>/home/me/prerolls</code>, mounted into two Docker
        containers at different places. A mapping tells Prerolls Max to swap the first path for the second when it talks
        to Plex.
      </figcaption>
    </figure>
  );
}

export function FolderMappingPage() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const servers = useMediaServers();
  const plexServers = (servers.data ?? []).filter((s) => s.type === "plex");
  const serverId = params.get("server") ?? (plexServers.length > 1 ? String(plexServers.find((s) => s.primary)?.id ?? plexServers[0]?.id) : null);
  const picked = plexServers.find((s) => String(s.id) === serverId);
  const base = serverId ? `/api/servers/${serverId}/folder-mapping` : "/settings/path-mappings";
  const current = useQuery({
    queryKey: ["path-mappings", serverId ?? "first"],
    queryFn: async () => (await api.get<{ mappings: PathMapping[] }>(base)).mappings,
  });
  const [rows, setRows] = useState<PathMapping[]>([]);
  const [errors, setErrors] = useState<RowErrors[]>([]);

  useEffect(() => {
    if (current.data) setRows(current.data.length ? current.data : []);
  }, [current.data]);

  const save = useMutation({
    mutationFn: (mappings: PathMapping[]) => api.put(base, { mappings }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["path-mappings"] });
      await queryClient.invalidateQueries({ queryKey: ["media-servers"] });
      toast({ tone: "success", title: picked ? `Folder mapping saved for ${picked.name}` : "Folder mapping saved" });
    },
  });
  const detect = useMutation({
    mutationFn: () =>
      api.post<{ found?: boolean; already_working?: boolean; message?: string; suggestions: PathMapping[] }>(
        serverId ? `/api/servers/${serverId}/folder-mapping/detect` : "/settings/path-mappings/detect",
        {},
        { timeoutMs: 90_000 },
      ),
  });

  const update = (i: number, key: keyof PathMapping, value: string) => {
    setRows((r) => r.map((row, j) => (j === i ? { ...row, [key]: value } : row)));
    setErrors((e) => e.map((err, j) => (j === i ? { ...err, [key]: undefined } : err)));
  };

  const submit = () => {
    const nextErrors: RowErrors[] = rows.map((row) => {
      const local = cleanFolderPath(row.local, { what: "Prerolls Max folder" });
      const plex = cleanFolderPath(row.plex, { what: "media server folder" });
      return { local: local.ok ? undefined : local.message, plex: plex.ok ? undefined : plex.message };
    });
    setErrors(nextErrors);
    if (nextErrors.some((e) => e.local || e.plex)) return;
    save.mutate(rows.map((r) => ({ local: r.local.trim(), plex: r.plex.trim() })));
  };

  if (current.isLoading) return <Loading />;
  if (current.isError) return <ErrorNotice error={current.error} onRetry={() => current.refetch()} />;

  return (
    <div className="stack">
      <p>
        Most people don't need this. You need it when Prerolls Max and your media server run on different computers or
        in different Docker containers, and see your intro folder under different paths.
      </p>
      <Example />
      {plexServers.length > 1 && (
        <Select
          label="Plex server"
          help="Each Plex server sees the intro folder in its own way, so each has its own mapping."
          value={serverId ?? ""}
          onChange={(v) => {
            setParams({ server: v });
            detect.reset();
          }}
          options={plexServers.map((s) => ({ value: String(s.id), label: s.name }))}
        />
      )}
      <div className="row">
        <Button icon={<FolderSearch size={18} aria-hidden="true" />} onClick={() => detect.mutate()} loading={detect.isPending}>
          Find it for me (Plex)
        </Button>
      </div>
      {detect.isError && <ErrorNotice error={detect.error} />}
      {detect.data && (
        detect.data.already_working ? (
          <Notice tone="success">Plex already sees your intro folder. You don't need a mapping.</Notice>
        ) : detect.data.suggestions.length ? (
          <Notice tone="info" title="Found it">
            {detect.data.suggestions.map((s) => (
              <p key={s.local}>
                <code>{s.local}</code> is <code>{s.plex}</code> for Plex.{" "}
                <Button size="sm" onClick={() => setRows((r) => [...r.filter((x) => x.local !== s.local), s])}>Use this</Button>
              </p>
            ))}
          </Notice>
        ) : (
          <Notice tone="warning">{detect.data.message || "Plex couldn't find your intro folder. Make sure it's added to Plex's Docker container, then try again or fill it in below."}</Notice>
        )
      )}
      <h3>Your mappings</h3>
      {!rows.length && <p className="muted">No mappings. Paths are sent to the media server as they are.</p>}
      <ul className="list">
        {rows.map((row, i) => (
          <li key={i} className="mapping-row">
            <TextField label="Prerolls Max sees" placeholder="/data/prerolls" value={row.local} onChange={(e) => update(i, "local", e.target.value)} error={errors[i]?.local} autoCapitalize="none" />
            <TextField label="Media server sees" placeholder="/media/prerolls" value={row.plex} onChange={(e) => update(i, "plex", e.target.value)} error={errors[i]?.plex} autoCapitalize="none" />
            <IconButton label="Remove this mapping" onClick={() => { setRows((r) => r.filter((_, j) => j !== i)); setErrors((e) => e.filter((_, j) => j !== i)); }}>
              <Trash2 size={18} aria-hidden="true" />
            </IconButton>
          </li>
        ))}
      </ul>
      <div className="form-actions">
        <Button icon={<Plus size={18} aria-hidden="true" />} onClick={() => { setRows((r) => [...r, { local: "", plex: "" }]); setErrors((e) => [...e, {}]); }}>
          Add a mapping
        </Button>
        <Button variant="primary" onClick={submit} loading={save.isPending}>
          Save
        </Button>
      </div>
      {save.isError && <ErrorNotice error={save.error} />}
    </div>
  );
}
