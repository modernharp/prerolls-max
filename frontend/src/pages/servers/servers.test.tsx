// Media Servers: friendly default names, names checked like the server does,
// and the edit form refusing a bad address or a name already in use before
// anything is sent.
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import { ToastProvider } from "../../components/Toast";
import { nameTaken, suggestName, type MediaServer } from "../../lib/mediaServers";
import { validateRule } from "../../lib/playlist";
import { AddServerDialog, EditServerDialog } from "./ServerDialogs";
import { PluginSection } from "./ServerCard";

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

const server = (id: number, name: string, type: MediaServer["type"] = "jellyfin"): MediaServer => ({
  id, name, type, type_label: type === "plex" ? "Plex" : type === "emby" ? "Emby" : "Jellyfin",
  url: `http://box${id}:8096`, enabled: true, primary: id === 1, version: null, has_key: true, plugin_key: null,
});

function mockFetch() {
  const calls: { url: string; method?: string; body: unknown }[] = [];
  vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
    calls.push({ url, method: init?.method, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    return new Response(JSON.stringify({ ...server(2, "Bedroom") }), { status: 200, headers: { "content-type": "application/json" } });
  });
  return calls;
}

afterEach(() => vi.unstubAllGlobals());

describe("server names", () => {
  it("suggests Jellyfin, then Jellyfin 2, ignoring case", () => {
    expect(suggestName([], "Jellyfin")).toBe("Jellyfin");
    expect(suggestName([server(1, "jellyfin")], "Jellyfin")).toBe("Jellyfin 2");
    expect(suggestName([server(1, "Jellyfin"), server(2, "JELLYFIN 2")], "Jellyfin")).toBe("Jellyfin 3");
  });

  it("spots a name already in use, but not the server's own", () => {
    const list = [server(1, "Living room"), server(2, "Bedroom")];
    expect(nameTaken("  living   ROOM ", list)).toBe(true); // spaces and case are ignored, like on the server
    expect(nameTaken("living room", list)).toBe(true);
    expect(nameTaken("Living room", list, 1)).toBe(false);
  });

  it("lets a playlist rule name one server", () => {
    expect(validateRule({ kind: "server", values: ["server:4"] })).toEqual([]);
    expect(validateRule({ kind: "server", values: ["server:x"] })).toEqual(["Pick at least one media server."]);
  });
});

describe("edit a server", () => {
  it("refuses a bad address and a duplicate name before sending", async () => {
    const calls = mockFetch();
    const list = [server(1, "Living room"), server(2, "Bedroom")];
    render(wrap(<EditServerDialog server={list[1] ?? null} servers={list} onClose={() => undefined} />));
    const user = userEvent.setup();
    const name = await screen.findByLabelText("Name");
    await user.clear(name);
    await user.type(name, "living room");
    const address = screen.getByLabelText("Jellyfin address");
    await user.clear(address);
    await user.type(address, "ftp://nope");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText('There\'s already a media server called "living room".')).toBeInTheDocument();
    expect(screen.getByText("The address must start with http:// or https://.")).toBeInTheDocument();
    expect(calls).toEqual([]);

    await user.clear(name);
    await user.type(name, "Guest room");
    await user.clear(address);
    await user.type(address, "box2");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ name: "Guest room" }));
  });
});

describe("add a server", () => {
  it("asks which kind, suggests a free name and sends the key as the token", async () => {
    const calls = mockFetch();
    render(wrap(<AddServerDialog open onOpenChange={() => undefined} servers={[server(1, "Jellyfin")]} />));
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /^Jellyfin/ }));
    expect(screen.getByLabelText("Name")).toHaveValue("Jellyfin 2");
    await user.type(screen.getByLabelText("Jellyfin address"), "http://jf2:8096");
    await user.type(screen.getByLabelText("API key"), "k".repeat(32));
    await user.click(screen.getByRole("button", { name: "Connect" }));
    await waitFor(() =>
      expect(calls.find((c) => c.url.endsWith("/api/servers"))?.body).toEqual({
        type: "jellyfin", name: "Jellyfin 2", url: "http://jf2:8096", token: "k".repeat(32),
      }),
    );
  });
});

describe("plugin on a server card", () => {
  const working = { connected: true, version: "2.1.0.0", protocol: "v2", last_seen_seconds_ago: 30, note: "The plugin is connected." };
  const mockFetch = () =>
    vi.stubGlobal("fetch", async (url: string) => {
      const body = url.includes("/api/capabilities") ? { servers: [] } : { detected: true, plugin: { version: "2.1.0.0" } };
      return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
    });

  it("is one line when it works, and opens its steps on demand", async () => {
    mockFetch();
    const user = userEvent.setup();
    render(wrap(<PluginSection server={server(1, "Living room")} plugin={working} loaded />));
    expect(screen.getByText("Working")).toBeInTheDocument();
    expect(screen.getByText("version 2.1.0.0")).toBeInTheDocument();
    expect(screen.queryByText("Download the plugin")).not.toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: "Show setup steps" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);
    expect(await screen.findByText("Download the plugin")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hide setup steps" })).toHaveAttribute("aria-expanded", "true");
  });

  it("shows the steps straight away when the plugin needs setting up", async () => {
    mockFetch();
    render(wrap(<PluginSection server={server(1, "Living room")} plugin={{ ...working, connected: false }} loaded />));
    expect(screen.getByText("Needs setting up")).toBeInTheDocument();
    expect(await screen.findByText("Download the plugin")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hide setup steps" })).toHaveAttribute("aria-expanded", "true");
  });

  it("stays closed for a switched-off server and while it's still checking", () => {
    mockFetch();
    const { unmount } = render(wrap(<PluginSection server={{ ...server(1, "Den"), enabled: false }} loaded />));
    expect(screen.queryByText("Download the plugin")).not.toBeInTheDocument();
    unmount();
    render(wrap(<PluginSection server={server(1, "Den")} loaded={false} />));
    expect(screen.queryByText("Download the plugin")).not.toBeInTheDocument();
  });
});
