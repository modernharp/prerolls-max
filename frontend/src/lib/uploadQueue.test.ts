import { MAX_UPLOAD_BYTES, NOT_A_VIDEO, TOO_BIG, canSend, fileKey, isRefusal, isVideoFile, mergeFiles, stateFromAnswer } from "./uploadQueue";
import { ApiError } from "./errors";
import { zonesDiffer, zoneOffsetMinutes } from "./timezones";

const file = (name: string, size = 10, type = "", lastModified = 1) => {
  const f = new File(["x"], name, { type, lastModified });
  Object.defineProperty(f, "size", { value: size });
  return f;
};

describe("upload queue", () => {
  it("recognises video files by type or extension", () => {
    expect(isVideoFile(file("a.mkv"))).toBe(true);
    expect(isVideoFile(file("clip", 10, "video/mp4"))).toBe(true);
    expect(isVideoFile(file("notes.txt", 10, "text/plain"))).toBe(false);
  });

  it("lists non-videos and files over 500 MB as refused, and drops repeats", () => {
    const a = file("a.mp4");
    const txt = file("b.txt");
    const big = file("big.mp4", MAX_UPLOAD_BYTES + 1);
    const result = mergeFiles([a], [a, txt, big, file("c.mov")]);
    expect(result.files.map((f) => f.name)).toEqual(["a.mp4", "b.txt", "big.mp4", "c.mov"]);
    expect(result.repeated).toBe(1);
    expect(result.refused).toEqual({ [fileKey(txt)]: NOT_A_VIDEO, [fileKey(big)]: TOO_BIG });
    expect(result.notVideo).toEqual(["b.txt"]);
    expect(result.tooLarge).toEqual(["big.mp4"]);
  });

  it("sends waiting and failed files, never refused, finished or duplicate ones", () => {
    expect(canSend(undefined)).toBe(true);
    expect(canSend({ status: "error", error: new ApiError({ kind: "network", message: "x" }) })).toBe(true);
    expect(canSend({ status: "refused", message: "x" })).toBe(false);
    expect(canSend({ status: "done" })).toBe(false);
    expect(canSend({ status: "duplicate", token: "t", existing: "A" })).toBe(false);
  });

  it("tells a refusal (the file itself) from a failure to send", () => {
    expect(isRefusal(new ApiError({ kind: "invalid", status: 422, message: "x" }))).toBe(true);
    expect(isRefusal(new ApiError({ kind: "invalid", status: 413, message: "x" }))).toBe(true);
    expect(isRefusal(new ApiError({ kind: "server", status: 500, message: "x" }))).toBe(false);
    expect(isRefusal(new ApiError({ kind: "network", message: "x" }))).toBe(false);
  });

  it("reads the server's answer", () => {
    expect(stateFromAnswer({ uploaded: true })).toEqual({ status: "done" });
    expect(stateFromAnswer({ duplicate: true, token: "t", existing: { id: 1, name: "Pumpkin" } })).toEqual({ status: "duplicate", token: "t", existing: "Pumpkin" });
    expect(stateFromAnswer({ skipped: true, message: "Already there." })).toEqual({ status: "skipped", message: "Already there." });
  });

  it("keeps two files with the same name from different folders apart", () => {
    expect(fileKey(file("a.mp4", 10, "", 1))).not.toBe(fileKey(file("a.mp4", 11, "", 1)));
  });
});

describe("time zones", () => {
  it("knows UTC has no offset and unknown zones return null", () => {
    expect(zoneOffsetMinutes("UTC")).toBe(0);
    expect(zoneOffsetMinutes("Not/AZone")).toBeNull();
    expect(zonesDiffer(null)).toBe(false);
  });
});
