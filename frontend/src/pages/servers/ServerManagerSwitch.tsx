// "Prerolls Max manages intros on this server" on each server card. Off means
// NeXroll keeps this server (Settings > Moving from NeXroll, "keep both"):
// Prerolls Max leaves its Plex intro list alone and its plugin adds nothing.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import type { MediaServer } from "../../lib/mediaServers";
import { nexrollKeys } from "../../lib/nexroll";
import { SwitchRow } from "../../components/Controls";
import { ErrorNotice } from "../../components/Notice";
import { useToast } from "../../components/Toast";

export function ServerManagerSwitch({ server }: { server: MediaServer }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const ours = server.managed_by !== "nexroll";
  const set = useMutation({
    mutationFn: (manager: "prerollsmax" | "nexroll") => api.put(`/api/servers/${server.id}/manager`, { manager }),
    onSuccess: async (_data, manager) => {
      await queryClient.invalidateQueries({ queryKey: ["media-servers"] });
      await queryClient.invalidateQueries({ queryKey: nexrollKeys.status });
      await queryClient.invalidateQueries({ queryKey: nexrollKeys.detect });
      toast({
        tone: "success",
        title: manager === "nexroll" ? `NeXroll manages ${server.name} now` : `Prerolls Max manages ${server.name} again`,
      });
    },
  });
  if (server.managed_by === undefined) return null;
  return (
    <>
      <SwitchRow
        label="Prerolls Max manages intros on this server"
        description={
          ours ? undefined : (
            <>
              NeXroll does. Prerolls Max leaves {server.type === "plex" ? "its intro list" : "it"} alone.{" "}
              <Link to="/settings#nexroll">About keeping both</Link>
            </>
          )
        }
        checked={ours}
        disabled={set.isPending}
        onChange={(on) => set.mutate(on ? "prerollsmax" : "nexroll")}
      />
      {set.isError && <ErrorNotice error={set.error} />}
    </>
  );
}
