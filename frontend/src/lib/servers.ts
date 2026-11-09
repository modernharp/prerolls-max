import { useServerStatus } from "./queries";
import type { ServerType } from "./capabilities";

export const SERVER_TYPES: ServerType[] = ["plex", "jellyfin", "emby"];

/** Every media server's status: which are set up, which are connected. */
export function useServerSummary() {
  const plex = useServerStatus("plex");
  const jellyfin = useServerStatus("jellyfin");
  const emby = useServerStatus("emby");
  const all = { plex, jellyfin, emby };
  const loading = SERVER_TYPES.some((t) => all[t].isLoading);
  const configured = SERVER_TYPES.filter((t) => all[t].data?.connected || all[t].data?.url || all[t].isError);
  const connected = SERVER_TYPES.filter((t) => all[t].data?.connected);
  return { all, loading, configured, connected };
}
