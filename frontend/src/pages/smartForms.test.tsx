// Forms for the smart features: problems show next to the field before
// anything is sent, and fixed values are sent in the server's shape.
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as RTooltip from "@radix-ui/react-tooltip";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import { ToastProvider } from "../components/Toast";
import { WatchFolderDialog } from "./videos/watch/WatchFolderDialog";
import { restoredText } from "./settings/BackupSection";
import { liveDescription } from "./videos/community/useCommunity";

function wrap(children: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <RTooltip.Provider>
        <ToastProvider>
          <MemoryRouter>{children}</MemoryRouter>
        </ToastProvider>
      </RTooltip.Provider>
    </QueryClientProvider>
  );
}

function mockFetch(handler: (url: string, init?: RequestInit) => unknown) {
  const calls: { url: string; body: unknown }[] = [];
  vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
    calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    const data = handler(url, init);
    return new Response(JSON.stringify(data ?? []), { status: 200, headers: { "content-type": "application/json" } });
  });
  return calls;
}

// Radix switches measure themselves; jsdom has no ResizeObserver.
class NoResize {
  observe() {}
  unobserve() {}
  disconnect() {}
}
beforeEach(() => vi.stubGlobal("ResizeObserver", NoResize));
afterEach(() => vi.unstubAllGlobals());

describe("watch folder form", () => {
  it("checks the folder like the server before sending", async () => {
    const calls = mockFetch((url) => (url.includes("watch-folders") ? { id: 1, path: "/downloads/intros" } : []));
    render(wrap(<WatchFolderDialog folder="new" onClose={() => undefined} />));
    const user = userEvent.setup();
    const box = await screen.findByLabelText("Folder");
    await user.type(box, "downloads/intros");
    await user.click(screen.getByRole("button", { name: "Start watching" }));
    expect(await screen.findByText(/Use the full path from the top/)).toBeInTheDocument();
    expect(calls.some((c) => c.url.includes("watch-folders"))).toBe(false);

    await user.clear(box);
    await user.type(box, "/downloads/intros");
    await user.click(screen.getByRole("button", { name: "Start watching" }));
    await waitFor(() => expect(calls.find((c) => c.url.includes("watch-folders"))?.body).toEqual({ path: "/downloads/intros", collection_id: null, mode: "link", recursive: true, enabled: true }));
  });
});

describe("plain summaries", () => {
  it("lists what a restore brought back", () => {
    expect(restoredText({ smart_settings: 1, intro_rules: 3, watch_folders: 1 })).toBe("the Playback settings, 3 rules and 1 watch folder");
    expect(restoredText({})).toBeNull();
  });

  it("uses the live count instead of an estimate", () => {
    const description = "The library NeXroll used: about 1,800 intro videos, many in Plex versions.";
    expect(liveDescription({ description, item_count: 1006 })).toBe("The library NeXroll used: 1,006 intro videos, many in Plex versions.");
    expect(liveDescription({ description, item_count: 0 })).toBe("The library NeXroll used: intro videos, many in Plex versions.");
  });
});
