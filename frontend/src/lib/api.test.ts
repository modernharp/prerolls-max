import { api, onAuthProblem } from "./api";
import { ApiError } from "./errors";

function respond(status: number, body: string, type = "application/json") {
  return vi.fn().mockResolvedValue(new Response(body, { status, headers: { "content-type": type } }));
}

async function failure(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (error) {
    return error as ApiError;
  }
  throw new Error("expected the call to fail");
}

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("returns JSON on success", async () => {
    vi.stubGlobal("fetch", respond(200, '{"a":1}'));
    await expect(api.get("/x")).resolves.toEqual({ a: 1 });
  });

  it("reads the contract error format", async () => {
    vi.stubGlobal(
      "fetch",
      respond(422, JSON.stringify({
        detail: "Check the address.",
        error: { code: "invalid_input", message: "Check the address.", hint: "Use http://", fields: { url: "Bad" }, request_id: "abc123" },
      })),
    );
    const error = await failure(api.post("/plex/connect", {}));
    expect(error).toBeInstanceOf(ApiError);
    expect(error.message).toBe("Check the address.");
    expect(error.hint).toBe("Use http://");
    expect(error.fields).toEqual({ url: "Bad" });
    expect(error.requestId).toBe("abc123");
  });

  it("turns an HTML page into a readable message, not 'Unexpected token <'", async () => {
    vi.stubGlobal("fetch", respond(200, "<!doctype html><p>proxy</p>", "text/html"));
    const error = await failure(api.get("/prerolls"));
    expect(error.kind).toBe("unexpected");
    expect(error.message).not.toMatch(/token/i);
  });

  it("explains a network failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const error = await failure(api.get("/prerolls"));
    expect(error.kind).toBe("network");
    expect(error.message).toBe("Can't reach Prerolls Max.");
  });

  it("hides technical details from old endpoints", async () => {
    vi.stubGlobal("fetch", respond(500, JSON.stringify({ detail: "Traceback (most recent call last): KeyError" })));
    const error = await failure(api.get("/stats"));
    expect(error.message).toBe("Something went wrong inside Prerolls Max.");
  });

  it("maps FastAPI's own 422 list to fields", async () => {
    vi.stubGlobal("fetch", respond(422, JSON.stringify({ detail: [{ loc: ["body", "name"], msg: "Field required" }] })));
    const error = await failure(api.post("/schedules", {}));
    expect(error.fields).toEqual({ name: "Field required" });
  });

  it("tells listeners when sign-in is needed", async () => {
    vi.stubGlobal("fetch", respond(401, JSON.stringify({ detail: "Authentication required" })));
    const seen: string[] = [];
    const stop = onAuthProblem((e) => seen.push(e.kind));
    await failure(api.get("/prerolls"));
    stop();
    expect(seen).toEqual(["signed_out"]);
  });

  it("recognises setup_required", async () => {
    vi.stubGlobal(
      "fetch",
      respond(401, JSON.stringify({ detail: "Set up first", error: { code: "setup_required", message: "Set up first" } })),
    );
    const error = await failure(api.get("/prerolls"));
    expect(error.kind).toBe("setup_required");
  });
});
