import { checkVideoLink } from "./videoLink";

// The same cases and messages as tests/test_link_import.py on the server.
describe("video links", () => {
  it.each([
    ["", "Paste a link to a video file."],
    ["ftp://example.com/a.mp4", "Use a link that starts with http:// or https://."],
    ["example.com/a.mp4", "Use a link that starts with http:// or https://."],
    ["https://user:pw@example.com/a.mp4", "Links with a user name or password in them can't be used."],
    ["https://www.youtube.com/watch?v=abc", "That's a video page, not a video file. Prerolls Max can't download from YouTube; it's against YouTube's terms."],
    ["https://youtu.be/abc", "That's a video page, not a video file. Prerolls Max can't download from YouTube; it's against YouTube's terms."],
    ["https://vimeo.com/123", "That's a video page, not a video file. Prerolls Max can't download from Vimeo; it's against Vimeo's terms."],
    ["https://example.com/live/index.m3u8", "That's a stream, not a file. Prerolls Max needs a link to one video file."],
    ["https://example.com/manifest.mpd", "That's a stream, not a file. Prerolls Max needs a link to one video file."],
  ])("refuses %s", (url, message) => {
    const check = checkVideoLink(url);
    expect(check.ok).toBe(false);
    expect(check.message).toBe(message);
  });

  it("explains what to do instead of a video site", () => {
    expect(checkVideoLink("https://youtu.be/x").hint).toBe("Download the file yourself if you have the rights to it, then upload it.");
  });

  it("keeps a direct link, trimmed", () => {
    expect(checkVideoLink("  https://example.com/intro.mp4 ")).toEqual({ ok: true, value: "https://example.com/intro.mp4" });
  });
});
