// Movie trailers page: what it says after testing against real Radarr and
// Sonarr, where YouTube refused every download and the page stayed silent.
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import { ResultNotice } from "./ResultNotice";
import { UpcomingList, missingServers } from "./TrailerLists";
import { libraryResult } from "./LibraryTrailers";
import type { TrailerSettings } from "./useTrailers";

function wrap(children: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

function mockFetch(handler: (url: string) => unknown) {
  vi.stubGlobal("fetch", async (url: string) => new Response(JSON.stringify(handler(url)), { status: 200, headers: { "content-type": "application/json" } }));
}

afterEach(() => vi.unstubAllGlobals());

const SETTINGS = { radarr_connected: true, sonarr_connected: true, days_ahead: 90 } as TrailerSettings;

describe("result notices", () => {
  it("shows a failure's error and hint, which the page used to drop", () => {
    render(<ResultNotice result={{ success: false, error: "That file has no YouTube cookies in it.", hint: "Export them again." }} />);
    expect(screen.getByRole("alert")).toHaveTextContent("That file has no YouTube cookies in it.");
    expect(screen.getByText("Export them again.")).toBeInTheDocument();
  });

  it("shows nothing when there's nothing to say", () => {
    const { container } = render(<ResultNotice result={{ success: true }} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("coming soon", () => {
  it("names the servers that didn't answer", () => {
    expect(missingServers(["Radarr 4K"], "movies")).toBe("Radarr 4K didn't answer, so its movies are missing below.");
    expect(missingServers(["Radarr", "Radarr 4K"], "movies")).toBe("Radarr and Radarr 4K didn't answer, so their movies are missing below.");
  });

  it("doesn't say nothing is coming when no Radarr answered", async () => {
    mockFetch((url) =>
      url.includes("radarr")
        ? { movies: [], failed_servers: ["Radarr", "Radarr 4K"], read_any: false }
        : { shows: [{ sonarr_id: 9, title: "Will Trent", season_number: 5, release_date: "2027-01-05", release_type: "new_season" }], failed_servers: [], read_any: true },
    );
    render(wrap(<UpcomingList settings={SETTINGS} />));
    expect(await screen.findByText("Prerolls Max can't reach Radarr and Radarr 4K right now")).toBeInTheDocument();
    expect(screen.queryByText("Nothing coming soon")).not.toBeInTheDocument();
    // Sonarr's date is release_date; the page used to read fields that don't exist.
    expect(await screen.findByText("Season 5 · Starts Jan 5, 2027 · No trailer yet")).toBeInTheDocument();
  });
});

describe("library trailers", () => {
  it("sums up a finished check", () => {
    expect(libraryResult({ running: false, result: { local_found: 1, downloaded: 0, failed: 3, candidates: 4 } })).toEqual({
      success: true,
      trouble: true,
      message: "Found 1 trailer file next to your movies. 3 trailers couldn't be downloaded. The list below says why.",
    });
    expect(libraryResult({ running: false, error: "Connect Radarr on the Movie trailers page first." })?.success).toBe(false);
    expect(libraryResult({ running: true })).toBeNull();
  });
});
