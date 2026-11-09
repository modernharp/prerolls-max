// A short video that lists what's coming soon, from Radarr and Sonarr. It's
// added to the intro videos ("Coming Soon Lists"), so a playlist can use it.
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Film } from "lucide-react";
import { api } from "../../../../lib/api";
import { cleanName } from "../../../../lib/validate";
import { Select } from "../../../../components/Select";
import { TextField } from "../../../../components/Field";
import { SwitchRow } from "../../../../components/Controls";
import { Button } from "../../../../components/Button";
import { ErrorNotice, Notice } from "../../../../components/Notice";
import { useSaveTrailerSettings, type TrailerSettings } from "./useTrailers";

interface Made {
  success?: boolean;
  path?: string;
  items_count?: number;
  total_eligible?: number;
  duration?: number;
  message?: string;
}

export function ComingSoonVideo({ settings }: { settings: TrailerSettings }) {
  const queryClient = useQueryClient();
  const saveSettings = useSaveTrailerSettings();
  const [layout, setLayout] = useState(settings.coming_soon_list_auto_regen_layout === "grid" ? "grid" : "list");
  const [source, setSource] = useState("both");
  const [name, setName] = useState("");
  const [nameError, setNameError] = useState<string>();
  const [stamp, setStamp] = useState(0);
  const make = useMutation({
    mutationFn: (serverName: string | undefined) =>
      api.post<Made>("/nexup/preroll/generate-coming-soon-list", {}, {
        query: { layout, source, server_name: serverName, duration: 10, max_items: 8, resolution: "1080" },
        timeoutMs: 5 * 60_000,
      }),
    onSuccess: () => {
      setStamp(Date.now());
      void queryClient.invalidateQueries({ queryKey: ["prerolls"] });
    },
  });
  const submit = () => {
    let serverName: string | undefined;
    if (name.trim()) {
      const r = cleanName(name, { what: "name", maxLen: 40 });
      if (!r.ok) {
        setNameError(r.message);
        return;
      }
      serverName = r.value;
    }
    setNameError(undefined);
    make.mutate(serverName);
  };
  const ready = settings.radarr_connected && Boolean(settings.storage_path);
  const file = layout === "grid" ? "coming_soon_grid.mp4" : "coming_soon_list.mp4";
  return (
    <div className="stack">
      <p className="muted">
        A 10-second video that lists up to eight movies and shows coming soon, with their dates. It&rsquo;s added to your
        intro videos in the &ldquo;Coming Soon Lists&rdquo; collection, so you can put it in a playlist.
      </p>
      <div className="form-grid">
        <Select
          label="Look"
          value={layout}
          onChange={setLayout}
          options={[
            { value: "list", label: "A list of titles" },
            { value: "grid", label: "Posters" },
          ]}
        />
        <Select
          label="What it lists"
          value={source}
          onChange={setSource}
          options={[
            { value: "both", label: "Movies and TV shows" },
            { value: "movies", label: "Movies only" },
            { value: "shows", label: "TV shows only" },
          ]}
        />
        <TextField
          label="Your cinema's name"
          optional
          placeholder="Our Home Cinema"
          help="Shown under “Coming soon”. Leave it empty to use your media server's name."
          value={name}
          error={nameError}
          onChange={(e) => setName(e.target.value)}
        />
      </div>
      <SwitchRow
        label="Make it again after each check"
        description="Keeps the list up to date once a day."
        checked={Boolean(settings.coming_soon_list_auto_regen)}
        disabled={saveSettings.isPending}
        onChange={(on) => saveSettings.mutate({ coming_soon_list_auto_regen: on, coming_soon_list_auto_regen_layout: layout })}
      />
      <div>
        <Button icon={<Film size={18} aria-hidden="true" />} loading={make.isPending} disabled={!ready} onClick={submit}>
          Make the video
        </Button>
      </div>
      {!ready && <p className="muted small">Connect Radarr and pick a folder for trailers first.</p>}
      {make.isPending && <p className="muted small">Making the video. Posters take a little longer.</p>}
      {make.isError && <ErrorNotice error={make.error} />}
      {make.data && !make.isPending && (
        <Notice tone={make.data.success === false ? "error" : "success"}>
          {make.data.success === false
            ? make.data.message || "The video couldn't be made."
            : `Made a ${make.data.duration ?? 10}-second video listing ${make.data.items_count ?? 0} of ${make.data.total_eligible ?? 0} titles coming soon. It's in your intro videos.`}
        </Notice>
      )}
      {make.data?.success && (
        <video className="player" controls muted preload="metadata" src={`/nexup/preroll/video/${file}?v=${stamp}`} aria-label="The coming soon video">
          Your browser can&rsquo;t play this video here.
        </video>
      )}
    </div>
  );
}
