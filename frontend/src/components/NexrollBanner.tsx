// "NeXroll is still running" on Home and Media Servers: the NeXroll plugin on a
// Jellyfin or Emby server, Plex's intro list changed by something else, or
// NeXroll answering on port 9393. With "keep both" chosen and no problems, a
// plain line says who manages what.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { nexrollKeys, useNexrollDetect } from "../lib/nexroll";
import { Button, ButtonLink } from "./Button";
import { Notice } from "./Notice";

export function NexrollBanner() {
  const queryClient = useQueryClient();
  const detect = useNexrollDetect();
  const dismiss = useMutation({
    mutationFn: (id: string) => api.post("/api/migrate/nexroll/detect/dismiss", { id }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: nexrollKeys.detect }),
  });
  const data = detect.data;
  if (!data) return null;
  const warnings = data.warnings;
  if (!warnings.length) {
    return data.alongside && data.summary ? (
      <Notice tone="info" title="NeXroll and Prerolls Max both run here.">
        <p>
          {data.summary} <Link to="/settings#nexroll">Change this</Link>
        </p>
      </Notice>
    ) : null;
  }
  return (
    <div className="stack-sm" aria-label="NeXroll">
      {warnings.map((w) => (
        <Notice
          key={w.id}
          tone={w.severity === "info" ? "info" : "warning"}
          title={w.title}
          action={
            <div className="form-actions">
              <ButtonLink size="sm" to={w.help}>
                {w.id.startsWith("plugin-") ? "How to remove it" : w.help.endsWith("running-both") ? "About keeping both" : "How to stop NeXroll"}
              </ButtonLink>
              <Button size="sm" variant="ghost" onClick={() => dismiss.mutate(w.id)} loading={dismiss.isPending && dismiss.variables === w.id}>
                Hide for a day
              </Button>
            </div>
          }
        >
          <p>{w.message}</p>
          <p>{w.fix}</p>
        </Notice>
      ))}
    </div>
  );
}
