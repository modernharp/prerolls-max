// Keys and tokens start hidden. "Show" reveals them (aria-pressed says so),
// pasting works, and the forms check them exactly as before.
import { useState } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import { ToastProvider } from "./Toast";
import { SecretField, SecretValue } from "./SecretField";
import { AddServerDialog } from "../pages/servers/ServerDialogs";

function Controlled() {
  const [value, setValue] = useState("");
  return <SecretField label="Your TMDB key" what="TMDB key" value={value} onChange={(e) => setValue(e.target.value)} />;
}

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

afterEach(() => vi.unstubAllGlobals());

describe("SecretField", () => {
  it("starts hidden, and Show and Hide switch it", async () => {
    const user = userEvent.setup();
    render(<Controlled />);
    const field = screen.getByLabelText("Your TMDB key");
    expect(field).toHaveAttribute("type", "password");
    expect(field).toHaveAttribute("autocomplete", "off");
    expect(field).toHaveAttribute("spellcheck", "false");
    expect(field).toHaveAttribute("autocapitalize", "none");

    const show = screen.getByRole("button", { name: "Show TMDB key" });
    expect(show).toHaveAttribute("aria-pressed", "false");
    expect(show).toHaveAttribute("aria-controls", field.id);
    await user.click(show);
    expect(field).toHaveAttribute("type", "text");
    const hide = screen.getByRole("button", { name: "Hide TMDB key" });
    expect(hide).toHaveAttribute("aria-pressed", "true");
    expect(hide).toHaveTextContent("Hide");
    await user.keyboard("{Enter}"); // the button keeps focus, so Enter switches it back
    expect(field).toHaveAttribute("type", "password");
    expect(screen.getByRole("button", { name: "Show TMDB key" })).toHaveAttribute("aria-pressed", "false");
  });

  it("takes a pasted key while hidden", async () => {
    const user = userEvent.setup();
    render(<Controlled />);
    const field = screen.getByLabelText("Your TMDB key");
    await user.click(field);
    await user.paste("abcd1234abcd1234");
    expect(field).toHaveValue("abcd1234abcd1234");
    expect(field).toHaveAttribute("type", "password");
  });

  it("names the field's label when no 'what' is given", () => {
    render(<SecretField label="API key" defaultValue="" />);
    expect(screen.getByRole("button", { name: "Show API key" })).toBeInTheDocument();
  });
});

describe("SecretValue (a new API key, shown once)", () => {
  it("hides the key until Show", async () => {
    const user = userEvent.setup();
    render(<SecretValue value="pmx_1234567890abcdef" what="new API key" />);
    expect(screen.queryByText("pmx_1234567890abcdef")).not.toBeInTheDocument();
    expect(screen.getByLabelText("new API key, hidden")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show new API key" }));
    expect(screen.getByText("pmx_1234567890abcdef")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hide new API key" })).toHaveAttribute("aria-pressed", "true");
  });
});

describe("a key field in a real form", () => {
  it("checks a hidden key the same way and sends a pasted one", async () => {
    const calls: { url: string; body: unknown }[] = [];
    vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
      calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      return new Response(JSON.stringify({ id: 2, name: "Jellyfin" }), { status: 200, headers: { "content-type": "application/json" } });
    });
    const user = userEvent.setup();
    render(wrap(<AddServerDialog open onOpenChange={() => undefined} servers={[]} />));
    await user.click(await screen.findByRole("button", { name: /^Jellyfin/ }));
    await user.type(screen.getByLabelText("Jellyfin address"), "http://jf:8096");
    const key = screen.getByLabelText("API key");
    expect(key).toHaveAttribute("type", "password");
    await user.type(key, "short");
    await user.click(screen.getByRole("button", { name: "Connect" }));
    expect(await screen.findByText("That API key looks too short. Copy the whole thing.")).toBeInTheDocument();
    expect(calls).toEqual([]);

    await user.clear(key);
    await user.click(key);
    await user.paste("k".repeat(32));
    await user.click(screen.getByRole("button", { name: "Connect" }));
    await waitFor(() =>
      expect(calls.find((c) => c.url.endsWith("/api/servers"))?.body).toEqual({
        type: "jellyfin", name: "Jellyfin", url: "http://jf:8096", token: "k".repeat(32),
      }),
    );
  });
});
