// "Add from a web link": the same check as check_link in
// app/backend/link_fetch.py, with the same messages (CONTRACTS.md §2), so a
// YouTube page or a stream is caught as it's pasted.
import type { Check } from "./validate";

const MAX_URL_LENGTH = 2000;

const VIDEO_SITES: Record<string, string> = {
  "youtube.com": "YouTube", "youtu.be": "YouTube", "youtube-nocookie.com": "YouTube",
  "vimeo.com": "Vimeo", "tiktok.com": "TikTok", "instagram.com": "Instagram",
  "facebook.com": "Facebook", "fb.watch": "Facebook", "twitter.com": "X", "x.com": "X",
  "dailymotion.com": "Dailymotion", "twitch.tv": "Twitch", "reddit.com": "Reddit",
  "streamable.com": "Streamable", "rumble.com": "Rumble", "bilibili.com": "Bilibili",
};
const STREAM_EXTENSIONS = [".m3u8", ".m3u", ".mpd", ".f4m", ".ism", ".isml"];

function videoSite(host: string): string | undefined {
  const h = host.toLowerCase().replace(/\.$/, "");
  const hit = Object.keys(VIDEO_SITES).find((domain) => h === domain || h.endsWith(`.${domain}`));
  return hit ? VIDEO_SITES[hit] : undefined;
}

export interface LinkCheck {
  ok: boolean;
  value: string;
  message?: string;
  hint?: string;
}

export function checkVideoLink(raw: string): LinkCheck {
  const text = (raw ?? "").trim();
  const fail = (message: string, hint?: string): LinkCheck => ({ ok: false, value: text, message, hint });
  if (!text) return fail("Paste a link to a video file.");
  if (text.length > MAX_URL_LENGTH) return fail("That link is too long.");
  let url: URL;
  try {
    url = new URL(text);
  } catch {
    return fail("Use a link that starts with http:// or https://.");
  }
  if ((url.protocol !== "http:" && url.protocol !== "https:") || !url.hostname) {
    return fail("Use a link that starts with http:// or https://.");
  }
  if (url.username || url.password) {
    return fail("Links with a user name or password in them can't be used.", "Use a link that opens the file without signing in.");
  }
  const site = videoSite(url.hostname);
  if (site) {
    return fail(
      `That's a video page, not a video file. Prerolls Max can't download from ${site}; it's against ${site}'s terms.`,
      "Download the file yourself if you have the rights to it, then upload it.",
    );
  }
  if (STREAM_EXTENSIONS.some((ext) => url.pathname.toLowerCase().endsWith(ext))) {
    return fail("That's a stream, not a file. Prerolls Max needs a link to one video file.", "Look for a download link that ends in .mp4 or .mkv.");
  }
  return { ok: true, value: text };
}

/** For forms that use the shared Check type. */
export function cleanVideoLink(raw: string): Check {
  const c = checkVideoLink(raw);
  return c.ok ? { ok: true, value: c.value } : { ok: false, message: c.message ?? "" };
}
