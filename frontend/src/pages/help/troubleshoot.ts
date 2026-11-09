// What the troubleshooter says for each server, device and situation.
import type { ServerType } from "../../lib/capabilities";

export interface Device {
  id: string;
  label: string;
  /** Advice for this device, or null when intros normally work there. */
  advice: string | null;
  works: "yes" | "workaround" | "no";
}

export const DEVICES: Record<ServerType, Device[]> = {
  plex: [
    { id: "web", label: "Web browser or Plex desktop app", works: "yes", advice: null },
    { id: "appletv", label: "Apple TV", works: "workaround", advice: "The 2026 Plex app for Apple TV skips intros when it's set to play only pre-rolls. In the app's settings, set \"Cinema trailers to play before movies\" to 1. Plex says a fix is in progress." },
    { id: "ios", label: "iPhone or iPad", works: "workaround", advice: "The 2026 Plex app for iPhone and iPad has the same problem as Apple TV. In the app's settings, set \"Cinema trailers to play before movies\" to 1." },
    { id: "androidtv", label: "Android TV, Fire TV or Shield", works: "workaround", advice: "The 2026 Plex app for Android TV and Fire TV skips intros unless \"Cinema trailers to play before movies\" is set to 1 in the app's settings." },
    { id: "roku", label: "Roku or a smart TV", works: "yes", advice: "These usually work. If not, check that \"Cinema trailers to play before movies\" in the app's settings isn't set to 0." },
    { id: "other", label: "Infuse, casting, DLNA or Plexamp", works: "no", advice: "These don't play Plex intros at all. Use the Plex app or a web browser instead." },
  ],
  jellyfin: [
    { id: "web", label: "Web browser or Jellyfin Media Player", works: "yes", advice: null },
    { id: "android", label: "Android phone or Android TV", works: "yes", advice: "Android TV plays intros before movies only, and only when you start from the beginning." },
    { id: "roku", label: "Roku", works: "workaround", advice: "The official Roku app has Cinema Mode off by default, and plays only the first intro. Turn Cinema Mode on in the app's settings." },
    { id: "kodi", label: "Kodi", works: "yes", advice: null },
    { id: "swiftfin", label: "Swiftfin (iPhone, iPad, Apple TV)", works: "no", advice: "Swiftfin doesn't play Jellyfin intros yet. On those devices, open Jellyfin in a web browser instead." },
    { id: "infuse", label: "Infuse", works: "no", advice: "Infuse doesn't play Jellyfin intros. There's no setting to change this." },
  ],
  emby: [
    { id: "web", label: "Web browser or Emby Theater", works: "yes", advice: null },
    { id: "mobile", label: "Emby app on a phone or tablet", works: "yes", advice: "Check that Cinema Intros is on in the app: Settings, then Playback." },
    { id: "tv", label: "Android TV or Fire TV", works: "yes", advice: "The TV app plays intros before movies only. Check Cinema Intros is on in the app's Playback settings." },
    { id: "roku", label: "Roku", works: "workaround", advice: "The Roku app has Cinema Intros off by default. Turn it on in the app's Playback settings." },
    { id: "samsung", label: "Samsung TV", works: "workaround", advice: "Some Samsung TVs show \"No compatible streams\" for intros. Convert the intro to H.264 MP4 and try again." },
    { id: "infuse", label: "Infuse", works: "no", advice: "Infuse doesn't play Emby intros. There's no setting to change this." },
  ],
};

export function situationAdvice(server: ServerType, kind: "movie" | "episode", resumed: boolean): string[] {
  const out: string[] = [];
  if (resumed) out.push("Intros only play when you start from the beginning. No media server plays them when you resume, or when you skip ahead in a list.");
  if (kind === "episode" && server === "plex") out.push("Plex plays intros before movies only, never before TV episodes. This can't be changed.");
  if (kind === "episode" && server === "jellyfin") out.push("For TV episodes, the Prerolls Max plugin must be installed and \"episodes\" turned on in its settings. Intros play before the first episode you start, not between episodes that play automatically.");
  if (kind === "episode" && server === "emby") out.push("In Emby, open Settings, then Cinema Intros, and turn on intros for episodes. Emby Premiere is needed.");
  if (server === "plex") out.push("In Plex, check that the movie's library has \"Enable Cinema Trailers\" turned on (Edit library, then Advanced).");
  if (server === "emby") out.push("Emby needs Emby Premiere for Cinema Intros, and Cinema Intros must be turned on in the server's settings.");
  return out;
}
