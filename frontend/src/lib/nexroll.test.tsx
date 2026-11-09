// Moving from NeXroll: the words the preview, the port field and the banner use.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import { ToastProvider } from "../components/Toast";
import { NexrollBanner } from "../components/NexrollBanner";
import { NexrollAlongside } from "../pages/settings/nexroll/NexrollAlongside";
import { addressWithPort, checkPort, missingSentence, previewSummary, serverLines, type AlongsideState, type Preview } from "./nexroll";

function wrap(children: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter>{children}</MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}

const preview = (over: Partial<Preview> = {}): Preview => ({
  source: { kind: "database", where: "/nexroll/nexroll.db", keys_left_out: false },
  counts: {
    collections: 3, intro_videos: 4, videos_found: 3, videos_missing: 1, videos_in_zip: 0, schedules: 3, playlists: 1,
    holidays: 0, genre_maps: 0, radarr: 0, sonarr: 0, api_keys: 2, users: 1,
  },
  servers: [
    { type: "plex", url: "http://192.168.1.5:32400", has_key: true, already_here: false },
    { type: "jellyfin", url: "http://192.168.1.6:8096", has_key: false, already_here: false },
    { type: "emby", url: "http://192.168.1.7:8096", has_key: true, already_here: true },
  ],
  keys: ["the Plex sign-in"],
  missing: { count: 1, folder: "D:\\Prerolls", examples: ["Snow Globe"] },
  names_taken: { collections: [], schedules: [], playlists: [] },
  library_empty: true,
  suggested_mode: "replace",
  skipped: [],
  left_behind: [],
  ...over,
});

function mockFetch(answer: unknown) {
  const calls: { url: string; method?: string; body: unknown }[] = [];
  vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
    calls.push({ url, method: init?.method, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    return new Response(JSON.stringify(answer), { status: 200, headers: { "content-type": "application/json" } });
  });
  return calls;
}

afterEach(() => vi.unstubAllGlobals());

describe("the preview in plain words", () => {
  it("counts what NeXroll has and how many videos are here", () => {
    expect(previewSummary(preview())).toBe("3 collections, 4 intro videos (3 found here, 1 missing), 3 schedules and 1 playlist");
    const all = preview({ counts: { ...preview().counts, videos_missing: 0, videos_found: 4, collections: 1 } });
    expect(previewSummary(all)).toBe("1 collection, 4 intro videos (all found here), 3 schedules and 1 playlist");
  });

  it("says which servers come with their key", () => {
    expect(serverLines(preview())).toEqual([
      "Plex at http://192.168.1.5:32400 (with its key)",
      "Jellyfin at http://192.168.1.6:8096 (no key: add it afterwards)",
      "Emby at http://192.168.1.7:8096 (already connected here)",
    ]);
  });

  it("names the folder Prerolls Max can't see", () => {
    expect(missingSentence({ count: 3, folder: "D:\\Prerolls" })).toBe(
      "NeXroll kept 3 videos in D:\\Prerolls, and Prerolls Max can't see that folder. Point it to where they are now.",
    );
    expect(missingSentence({ count: 0, folder: null })).toBeNull();
  });
});

describe("the port field", () => {
  it("checks the port like the server does", () => {
    expect(checkPort("", true)).toBe("Enter a port number.");
    expect(checkPort("94a", true)).toBe("Use digits only, like 9494.");
    expect(checkPort("80", true)).toBe("Pick a port between 1024 and 65535.");
    expect(checkPort("9393", true)).toBe("9393 is NeXroll's port. Pick another one, like 9494.");
    expect(checkPort("9393", false)).toBeUndefined();
    expect(checkPort(" 9494 ", true)).toBeUndefined();
  });

  it("shows the new address", () => {
    expect(addressWithPort(9494, { protocol: "http:", hostname: "192.168.1.20" } as Location)).toBe("http://192.168.1.20:9494");
  });
});

const alongside = (over: Partial<AlongsideState["port"]> = {}): AlongsideState => ({
  mode: "alongside",
  servers: [
    { id: 1, name: "Living room Plex", type: "plex", manager: "nexroll" },
    { id: 2, name: "Jellyfin 12", type: "jellyfin", manager: "prerollsmax" },
  ],
  summary: "NeXroll manages Living room Plex; Prerolls Max manages Jellyfin 12.",
  conflicts: [],
  port: { running: 9393, configured: 9494, source: "settings", saved: 9494, in_docker: false, restart_needed: true, ...over },
});

describe("keeping both", () => {
  it("asks for a restart and shows who manages each server", () => {
    render(wrap(<NexrollAlongside state={alongside()} />));
    expect(screen.getByText("Restart needed")).toBeInTheDocument();
    expect(screen.getByLabelText("Who manages intros on Living room Plex")).toHaveValue("nexroll");
    expect(screen.getByLabelText("Who manages intros on Jellyfin 12")).toHaveValue("prerollsmax");
  });

  it("refuses NeXroll's port before saving", async () => {
    const calls = mockFetch({});
    render(wrap(<NexrollAlongside state={alongside({ restart_needed: false, saved: null, configured: 9393 })} />));
    const field = screen.getByLabelText("Prerolls Max's port");
    await userEvent.clear(field);
    await userEvent.type(field, "9393");
    await userEvent.click(screen.getByRole("button", { name: "Save port" }));
    expect(screen.getByText("9393 is NeXroll's port. Pick another one, like 9494.")).toBeInTheDocument();
    expect(calls).toEqual([]);
  });

  it("tells Docker users to change the port mapping instead", () => {
    render(wrap(<NexrollAlongside state={alongside({ in_docker: true, source: "environment", restart_needed: false })} />));
    expect(screen.getByText(/change the port mapping instead/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Prerolls Max's port")).toBeNull();
  });

  it("hands a server to NeXroll from the table", async () => {
    const calls = mockFetch({ id: 2, managed_by: "nexroll" });
    render(wrap(<NexrollAlongside state={alongside()} />));
    await userEvent.selectOptions(screen.getByLabelText("Who manages intros on Jellyfin 12"), "nexroll");
    expect(calls.at(-1)).toMatchObject({ url: "/api/servers/2/manager", method: "PUT", body: { manager: "nexroll" } });
  });
});

describe("the NeXroll banner", () => {
  it("says what's wrong and how to fix it", async () => {
    mockFetch({
      alongside: false, summary: null, servers: [],
      warnings: [{
        id: "plugin-2", severity: "warning", server: "Jellyfin 12",
        title: "Jellyfin 12 still has the NeXroll Intros plugin.",
        message: "Intros will play twice: once from NeXroll, once from Prerolls Max.",
        fix: "Remove it in Jellyfin: Dashboard > Plugins > NeXroll Intros > Uninstall, then restart Jellyfin.",
        help: "/help/moving-from-nexroll#help-remove-the-nexroll-plugin",
      }],
    });
    render(wrap(<NexrollBanner />));
    expect(await screen.findByText("Jellyfin 12 still has the NeXroll Intros plugin.")).toBeInTheDocument();
    expect(screen.getByText(/Intros will play twice/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "How to remove it" })).toHaveAttribute("href", "/help/moving-from-nexroll#help-remove-the-nexroll-plugin");
  });

  it("is a plain note when both run on purpose without problems", async () => {
    mockFetch({ alongside: true, summary: "NeXroll manages Living room Plex; Prerolls Max manages Jellyfin 12.", servers: [], warnings: [] });
    render(wrap(<NexrollBanner />));
    expect(await screen.findByText("NeXroll and Prerolls Max both run here.")).toBeInTheDocument();
    expect(screen.getByText(/NeXroll manages Living room Plex/)).toBeInTheDocument();
  });

  it("stays out of the way when NeXroll is gone", async () => {
    const calls = mockFetch({ alongside: false, summary: null, servers: [], warnings: [] });
    render(wrap(<NexrollBanner />));
    await vi.waitFor(() => expect(calls.length).toBe(1));
    expect(screen.queryByText(/NeXroll/)).toBeNull();
  });
});
