// The upload list: every file has its own status line. Files that can't be
// added say "Not added" and why, and are never sent (again); a file that's
// already in the library asks Skip or Add anyway.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as RTooltip from "@radix-ui/react-tooltip";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import { ToastProvider } from "../../components/Toast";
import { ApiError } from "../../lib/errors";
import { MAX_UPLOAD_BYTES, sendUpload } from "../../lib/uploadQueue";
import { UploadDialog } from "./UploadDialog";

vi.mock("../../lib/uploadQueue", async (original) => ({
  ...(await original<typeof import("../../lib/uploadQueue")>()),
  sendUpload: vi.fn(),
}));
const send = vi.mocked(sendUpload);

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

const file = (name: string, size = 10, type = "") => {
  const f = new File(["x"], name, { type, lastModified: 1 });
  Object.defineProperty(f, "size", { value: size });
  return f;
};

let calls: { url: string; body: unknown }[] = [];
beforeEach(() => {
  calls = [];
  send.mockReset();
  vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
    calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    const data = url.includes("/staged/") ? { skipped: true } : [];
    return new Response(JSON.stringify(data), { status: 200, headers: { "content-type": "application/json" } });
  });
});
afterEach(() => vi.unstubAllGlobals());

const rowFor = (name: string) => screen.getByText(name).closest("li") as HTMLElement;

describe("upload list", () => {
  it("lists files that can't be added as Not added and leaves them out of Upload", async () => {
    render(wrap(<UploadDialog open onOpenChange={() => undefined} initialFiles={[file("notes.txt", 10, "text/plain"), file("huge.mp4", MAX_UPLOAD_BYTES + 1), file("intro.mp4")]} />));
    expect(within(rowFor("notes.txt")).getByText(/Not added — not a video file\./)).toBeInTheDocument();
    expect(within(rowFor("huge.mp4")).getByText(/Not added — bigger than 500 MB/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload 1 video" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove notes.txt from the list" })).toBeInTheDocument();
  });

  it("doesn't offer to send a file the server turned down again", async () => {
    send.mockImplementation(() => ({
      promise: Promise.reject(new ApiError({ kind: "invalid", status: 422, message: "That file isn't a video, even though its name ends in .mp4." })),
      abort: () => undefined,
    }));
    const user = userEvent.setup();
    render(wrap(<UploadDialog open onOpenChange={() => undefined} initialFiles={[file("picture.mp4")]} />));
    await user.click(screen.getByRole("button", { name: "Upload 1 video" }));
    expect(await within(rowFor("picture.mp4")).findByText(/Not added — that file isn't a video/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Upload/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Done" })).toBeInTheDocument();
    expect(send).toHaveBeenCalledTimes(1);

    // Clearing the list starts again.
    await user.click(screen.getByRole("button", { name: "Clear list" }));
    expect(screen.queryByText("picture.mp4")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload" })).toBeInTheDocument();
  });

  it("keeps a file that didn't get through (no network) to try again", async () => {
    send.mockImplementation(() => ({ promise: Promise.reject(new ApiError({ kind: "network", message: "Prerolls Max didn't answer." })), abort: () => undefined }));
    const user = userEvent.setup();
    render(wrap(<UploadDialog open onOpenChange={() => undefined} initialFiles={[file("intro.mp4")]} />));
    await user.click(screen.getByRole("button", { name: "Upload 1 video" }));
    expect(await within(rowFor("intro.mp4")).findByText(/sent again when you press Upload/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload 1 video" })).toBeInTheDocument();
  });

  it("asks about a video that's already in the library, with Skip as the default", async () => {
    send.mockImplementation(() => ({
      promise: Promise.resolve({ uploaded: false, duplicate: true, token: "tok_abcdefghijklmnop", existing: { id: 3, name: "Pumpkin Intro" } }),
      abort: () => undefined,
    }));
    const user = userEvent.setup();
    render(wrap(<UploadDialog open onOpenChange={() => undefined} initialFiles={[file("pumpkin copy.mp4")]} />));
    await user.click(screen.getByRole("button", { name: "Upload 1 video" }));
    const row = rowFor("pumpkin copy.mp4");
    expect(await within(row).findByText('Already in your library as "Pumpkin Intro".')).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: "Add anyway" })).toBeInTheDocument();
    await user.click(within(row).getByRole("button", { name: "Skip" }));
    await waitFor(() => expect(calls.find((c) => c.url.includes("/prerolls/upload/staged/tok_abcdefghijklmnop"))?.body).toEqual({ action: "skip" }));
    expect(await within(row).findByText(/Skipped\. It's already in your library as "Pumpkin Intro"\./)).toBeInTheDocument();
    const form = send.mock.calls[0]?.[1] as FormData;
    expect(form.get("if_duplicate")).toBe("ask");
  });
});
