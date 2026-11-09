// "Try it" shows the answer for the title that was asked about, and no other.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { RulePreview } from "./RulePreview";

function wrap(children: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  vi.stubGlobal("fetch", async (url: string) => {
    const data = url.includes("/api/rules/preview")
      ? { excluded: false, matched: { id: 1, name: "Kids" }, explanation: "The rule Kids matches.", would_play: [], pool: [], count: 1, order: "random", checks: [], fallback: null }
      : { families: [] };
    return new Response(JSON.stringify(data), { status: 200, headers: { "content-type": "application/json" } });
  });
});
afterEach(() => vi.unstubAllGlobals());

describe("Try it", () => {
  it("drops the previous answer once the details change or a year can't be read", async () => {
    const user = userEvent.setup();
    render(wrap(<RulePreview />));
    await user.type(screen.getByLabelText(/Year/), "1994");
    await user.click(screen.getByRole("button", { name: "Show what would play" }));
    expect(await screen.findByText("The rule Kids matches.")).toBeInTheDocument();

    await user.clear(screen.getByLabelText(/Year/));
    await user.type(screen.getByLabelText(/Year/), "19x4");
    expect(screen.queryByText("The rule Kids matches.")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show what would play" }));
    expect(await screen.findByText(/year/i, { selector: ".field-error, .field-error *" })).toBeInTheDocument();
    expect(screen.queryByText("The rule Kids matches.")).not.toBeInTheDocument();
  });
});
