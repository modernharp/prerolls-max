// "Play a test": tells people exactly how to check that an intro plays,
// then records the answer or sends them to the troubleshooter. Or Prerolls
// Max asks any of the servers itself what it would play (ServerPlayTest).
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { isMissingFeature } from "../lib/errors";
import { keys } from "../lib/queries";
import { setTestPlayed } from "../lib/prefs";
import { SERVER_NAMES, type ServerType } from "../lib/capabilities";
import { Button } from "./Button";
import { ErrorNotice, Notice } from "./Notice";
import { ServerPlayTest } from "./ServerPlayTest";
import { useToast } from "./Toast";

const STEPS: Record<ServerType, string[]> = {
  plex: [
    "Open Plex in a web browser (app.plex.tv) or the Plex desktop app.",
    "Pick any movie and play it from the start, not from where you left off.",
    "Your intro should play first, then the movie.",
  ],
  jellyfin: [
    "Open Jellyfin in a web browser.",
    "Pick any movie and play it from the start.",
    "Your intro should play first, then the movie.",
  ],
  emby: [
    "Open Emby in a web browser.",
    "Pick any movie and play it from the start.",
    "Your intro should play first, then the movie.",
  ],
};

export function TestPlay({ servers, onDone }: { servers: ServerType[]; onDone?: () => void }) {
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  const server = servers[0] ?? "plex";
  const target = servers.length > 1 ? "your media servers" : SERVER_NAMES[server];

  const apply = useMutation({ mutationFn: () => api.post("/scheduler/run-now", {}, { timeoutMs: 60_000 }) });
  const finish = useMutation({
    mutationFn: async () => {
      try {
        await api.post("/onboarding/complete", {});
      } catch (error) {
        if (!isMissingFeature(error)) throw error;
      }
    },
    onSuccess: async () => {
      setTestPlayed(true);
      await queryClient.invalidateQueries({ queryKey: keys.onboarding });
      toast({ tone: "success", title: "Your intros are working", description: "That's setup done. Home will show if anything stops working." });
      onDone?.();
    },
  });

  return (
    <div className="stack">
      <Button onClick={() => apply.mutate()} loading={apply.isPending}>
        Send my intros to {target} now
      </Button>
      {apply.isSuccess && <Notice tone="success">Done. {servers.length > 1 ? "Your media servers have" : `${target} has`} your current intros.</Notice>}
      {apply.isError && <ErrorNotice error={apply.error} />}
      <ol className="numbered">
        {STEPS[server].map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ol>
      {server === "plex" && (
        <Notice tone="warning" title="Using the Plex app on Apple TV, iPhone, Android TV or Fire TV?">
          The 2026 versions of these apps skip intros. In the app, open Settings, then set "Cinema trailers to play before
          movies" to 1. The web app always works.
        </Notice>
      )}
      <details className="card details-card">
        <summary>
          <strong>Or let Prerolls Max ask the server</strong>
          <span className="muted small"> It asks what would play before a movie you pick. Nothing starts playing.</span>
        </summary>
        <ServerPlayTest />
      </details>
      {finish.isError && <ErrorNotice error={finish.error} />}
      <div className="form-actions">
        <Button variant="primary" onClick={() => finish.mutate()} loading={finish.isPending}>
          It played
        </Button>
        <Button onClick={() => navigate("/help/troubleshoot")}>It didn't play</Button>
      </div>
    </div>
  );
}
