// "What would play": asks Prerolls Max to run the playlist's rules as if a
// movie or episode were starting on a given server, right now.
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, CircleSlash, CornerDownRight } from "lucide-react";
import type { Block } from "../../../../lib/playlist";
import { Select } from "../../../../components/Select";
import { TextField } from "../../../../components/Field";
import { Button } from "../../../../components/Button";
import { ErrorNotice } from "../../../../components/Notice";
import { evaluatePlaylist } from "./usePlaylists";
import { describeStep, type Lookup } from "./playlistText";

export function PlaylistPreview({ blocks, lookup }: { blocks: Block[]; lookup: Lookup }) {
  const [server, setServer] = useState("jellyfin");
  const [mediaType, setMediaType] = useState("movie");
  const [genres, setGenres] = useState("");
  const run = useMutation({ mutationFn: () => evaluatePlaylist(blocks, { server, media_type: mediaType, genres }) });

  return (
    <section className="card stack" aria-labelledby="preview-title">
      <h2 id="preview-title">What would play</h2>
      <p className="muted">Pretend something is starting now, and see which steps play.</p>
      <div className="form-grid">
        <Select
          label="On"
          value={server}
          onChange={setServer}
          options={[
            { value: "plex", label: "Plex" },
            { value: "jellyfin", label: "Jellyfin" },
            { value: "emby", label: "Emby" },
          ]}
        />
        <Select
          label="Before"
          value={mediaType}
          onChange={setMediaType}
          options={[
            { value: "movie", label: "A movie" },
            { value: "episode", label: "A TV episode" },
          ]}
        />
        <TextField
          label="Its genres"
          optional
          placeholder="Horror, Comedy"
          help={server === "plex" ? "Plex doesn't say, so this is ignored on Plex." : "Separate several with commas."}
          value={genres}
          onChange={(e) => setGenres(e.target.value)}
          disabled={server === "plex"}
        />
      </div>
      <div>
        <Button onClick={() => run.mutate()} loading={run.isPending} disabled={!blocks.length}>
          Show what would play
        </Button>
      </div>
      {run.isError && <ErrorNotice error={run.error} />}
      {run.data && (
        <ol className="preview-list" aria-live="polite">
          {run.data.blocks.map((r, i) => (
            <li key={i} className={r.outcome === "skipped" ? "skipped" : ""}>
              {r.outcome === "plays" ? (
                <CheckCircle2 size={20} className="status-ok" aria-hidden="true" />
              ) : r.outcome === "otherwise" ? (
                <CornerDownRight size={20} className="status-warn" aria-hidden="true" />
              ) : (
                <CircleSlash size={20} className="muted" aria-hidden="true" />
              )}
              <div className="grow">
                <strong>Step {i + 1}: </strong>
                {r.outcome === "skipped"
                  ? "Nothing plays here."
                  : r.block
                    ? describeStep(r.block, lookup)
                    : describeStep(blocks[i] ?? { type: "" }, lookup)}
                {r.outcome === "otherwise" && <div className="muted small">The rule wasn't met, so the Otherwise step plays.</div>}
                {r.outcome === "skipped" && <div className="muted small">The rule wasn't met and there's no Otherwise step.</div>}
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
