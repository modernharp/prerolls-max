// Default intros: what plays when no schedule is on.
import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { keys, useCategories, useFiller } from "../../lib/queries";
import { Select } from "../../components/Select";
import { SwitchRow } from "../../components/Controls";
import { Button } from "../../components/Button";
import { ErrorNotice, Loading, Notice } from "../../components/Notice";
import { useToast } from "../../components/Toast";
import { HelpButton } from "../../components/HelpPanel";
import { usePrefs } from "../../lib/prefs";
import { usePlaylists } from "../settings/advanced/playlists/usePlaylists";

export function DefaultIntros() {
  const filler = useFiller();
  const categories = useCategories();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [enabled, setEnabled] = useState(false);
  const [collection, setCollection] = useState("");
  const [error, setError] = useState<string>();
  const { advanced } = usePrefs();
  const playlists = usePlaylists();

  useEffect(() => {
    if (!filler.data) return;
    setEnabled(filler.data.enabled);
    if (filler.data.type === "category" && filler.data.category_id) setCollection(String(filler.data.category_id));
    else if (filler.data.type === "sequence" && filler.data.sequence_id) setCollection(`p${filler.data.sequence_id}`);
    else setCollection("");
  }, [filler.data]);

  const isPlaylist = collection.startsWith("p");
  const save = useMutation({
    mutationFn: () =>
      api.put(
        "/settings/filler",
        !enabled
          ? { enabled: false }
          : isPlaylist
            ? { enabled: true, type: "sequence", sequence_id: Number(collection.slice(1)) }
            : { enabled: true, type: "category", category_id: Number(collection) },
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: keys.filler });
      toast({ tone: "success", title: enabled ? "Default intros are on" : "Default intros are off" });
    },
  });

  const submit = () => {
    if (enabled && !collection) {
      setError("Pick the collection to play when nothing else is scheduled.");
      return;
    }
    setError(undefined);
    save.mutate();
  };

  if (filler.isLoading) return <Loading />;
  if (filler.isError) return <ErrorNotice error={filler.error} onRetry={() => filler.refetch()} />;
  const otherType = filler.data && filler.data.enabled && !["category", "sequence"].includes(filler.data.type);
  const options = [
    ...(categories.data ?? []).filter((c) => !c.is_system).map((c) => ({ value: String(c.id), label: c.name })),
    ...(advanced || isPlaylist ? (playlists.data ?? []).map((p) => ({ value: `p${p.id}`, label: `Playlist: ${p.name}` })) : []),
  ];

  return (
    <section className="card section" aria-labelledby="defaults-title">
      <div className="row">
        <h2 id="defaults-title">Default intros</h2>
        <HelpButton slug="schedules" label="Help about default intros" />
      </div>
      <p className="muted">
        These play whenever no schedule is on, so there's always an intro before a movie. A schedule that's on always
        takes over from them.
      </p>
      {otherType && (
        <Notice tone="info">
          Your default intros are set up in a way this page can't show (a single video or a video maker video). Saving
          here replaces that with what you pick below.
        </Notice>
      )}
      <div className="stack">
        <SwitchRow label="Play default intros" checked={enabled} onChange={setEnabled} />
        {enabled && (
          <Select
            label={advanced ? "Collection or playlist" : "Collection"}
            value={collection}
            onChange={(v) => {
              setCollection(v);
              setError(undefined);
            }}
            options={options}
            placeholder="Choose a collection"
            error={error}
          />
        )}
        {save.isError && <ErrorNotice error={save.error} />}
        <div className="form-actions">
          <Button variant="primary" onClick={submit} loading={save.isPending}>
            Save default intros
          </Button>
        </div>
      </div>
    </section>
  );
}
