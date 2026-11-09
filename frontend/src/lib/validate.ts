// The same input checks as app/backend/validation.py, with the same messages,
// so people see a problem while they type instead of after saving.
// Keep the two files in step (CONTRACTS.md §2).

export type Check<T = string> = { ok: true; value: T } | { ok: false; message: string };

const ok = <T,>(value: T): Check<T> => ({ ok: true, value });
const fail = (message: string): Check<never> => ({ ok: false, message });

// Control characters: tabs, newlines and other invisible codes.
const CONTROL = /[\x00-\x1f\x7f]/;
const hasSpace = (text: string) => /\s/.test(text);

// ---------------------------------------------------------------------------
// Addresses
// ---------------------------------------------------------------------------

export function cleanServerUrl(
  value: string,
  { service = "the server", defaultPort }: { service?: string; defaultPort?: number } = {},
): Check {
  if (typeof value !== "string" || !value.trim()) return fail(`Enter the address of ${service}.`);
  let text = value.trim();
  if (hasSpace(text)) return fail("The address can't contain spaces.");
  if (text.length > 2048) return fail("That address is too long.");
  if (!text.includes("://")) {
    // "plex:32400" is a host and port; "javascript:..." or "file:..." is a scheme.
    if (/^[A-Za-z][A-Za-z0-9+.-]*:(?!\d)/.test(text)) return fail("The address must start with http:// or https://.");
    text = "http://" + text;
  }
  const m = /^([^:/?#]+):\/\/([^/?#]*)([^?#]*)(?:\?([^#]*))?(?:#(.*))?$/.exec(text);
  if (!m) return fail("The address must start with http:// or https://.");
  const scheme = (m[1] ?? "").toLowerCase();
  const netloc = m[2] ?? "";
  const path = m[3] ?? "";
  const query = m[4] ?? "";
  const fragment = m[5] ?? "";
  if (scheme !== "http" && scheme !== "https") return fail("The address must start with http:// or https://.");

  const at = netloc.lastIndexOf("@");
  const hostport = at >= 0 ? netloc.slice(at + 1) : netloc;
  let host = hostport;
  let port = "";
  if (hostport.startsWith("[")) {
    const close = hostport.indexOf("]");
    host = close > 0 ? hostport.slice(1, close) : "";
    const rest = close > 0 ? hostport.slice(close + 1) : "";
    port = rest.startsWith(":") ? rest.slice(1) : "";
  } else if (hostport.includes(":")) {
    host = hostport.slice(0, hostport.lastIndexOf(":"));
    port = hostport.slice(hostport.lastIndexOf(":") + 1);
  }
  if (!host) return fail("Add the computer name or IP address, like http://192.168.1.10:32400.");
  if (port && (!/^\d+$/.test(port) || Number(port) < 1 || Number(port) > 65535)) {
    return fail("The port number must be between 1 and 65535.");
  }
  if (at >= 0) return fail("Leave the user name and password out of the address.");
  if (query || fragment) return fail("Remove everything after ? or # from the address.");
  const finalNetloc = !port && defaultPort ? `${netloc}:${defaultPort}` : netloc;
  return ok(`${scheme}://${finalNetloc}${path.replace(/\/+$/, "")}`);
}

// ---------------------------------------------------------------------------
// Tokens and keys
// ---------------------------------------------------------------------------

export function cleanToken(
  value: string,
  { what = "token", minLen = 8, maxLen = 512 }: { what?: string; minLen?: number; maxLen?: number } = {},
): Check {
  if (typeof value !== "string" || !value.trim()) return fail(`Paste the ${what}.`);
  const text = value.trim().replace(/^"+|"+$/g, "").replace(/^'+|'+$/g, "").trim();
  if (hasSpace(text)) return fail(`The ${what} can't contain spaces. Copy it again without extra text.`);
  if (CONTROL.test(text)) return fail(`The ${what} contains characters that can't be part of a ${what}.`);
  if (text.length < minLen) return fail(`That ${what} looks too short. Copy the whole thing.`);
  if (text.length > maxLen) return fail(`That ${what} looks too long. Copy only the ${what}.`);
  return ok(text);
}

export const cleanApiKey = (value: string) => cleanToken(value, { what: "API key", minLen: 16 });

// ---------------------------------------------------------------------------
// Names
// ---------------------------------------------------------------------------

export function cleanName(value: string, { what = "name", maxLen = 100 }: { what?: string; maxLen?: number } = {}): Check {
  if (typeof value !== "string") return fail(`Enter a ${what}.`);
  const text = value.split(/\s+/).filter(Boolean).join(" ").normalize("NFC");
  if (!text) return fail(`Enter a ${what}.`);
  if (CONTROL.test(text)) return fail(`The ${what} contains characters that can't be used.`);
  if (text.length > maxLen) return fail(`Keep the ${what} to ${maxLen} characters or fewer.`);
  return ok(text);
}

const WIN_RESERVED = new Set([
  "CON", "PRN", "AUX", "NUL",
  ...Array.from({ length: 9 }, (_, i) => `COM${i + 1}`),
  ...Array.from({ length: 9 }, (_, i) => `LPT${i + 1}`),
]);

/** A file name (no folders). Plex separates intros with "," and ";", so those are out too. */
export function cleanFilename(value: string, { maxLen = 150 }: { maxLen?: number } = {}): Check {
  const named = cleanName(value, { what: "file name", maxLen });
  if (!named.ok) return named;
  const text = named.value;
  const bad = [...new Set(text.match(/[\\/:*?"<>|,;]/g) ?? [])].sort();
  if (bad.length) return fail("File names can't contain " + bad.join(" ") + ".");
  if (text === "." || text === ".." || text.endsWith(".") || text.endsWith(" ")) {
    return fail("File names can't end with a dot or a space.");
  }
  if (WIN_RESERVED.has((text.split(".")[0] ?? "").toUpperCase())) {
    return fail(`"${text}" is a reserved name on Windows. Pick another.`);
  }
  return ok(text);
}

// ---------------------------------------------------------------------------
// Folders
// ---------------------------------------------------------------------------

export function cleanFolderPath(value: string, { what = "folder" }: { what?: string } = {}): Check {
  if (typeof value !== "string" || !value.trim()) return fail(`Enter the ${what}.`);
  const text = value.trim().replace(/^"+|"+$/g, "").replace(/^'+|'+$/g, "");
  if (text.includes("\0") || CONTROL.test(text)) return fail(`The ${what} contains characters that can't be part of a path.`);
  if (text.length > 4096) return fail(`That ${what} path is too long.`);
  if (/^(https?|smb|nfs):\/\//.test(text)) {
    return fail("Enter a folder path, not a web or network address. Map the share as a folder first.");
  }
  const windows = /^[A-Za-z]:[\\/]/.test(text) || text.startsWith("\\\\");
  if (!windows && !text.startsWith("/")) {
    return fail("Use the full path from the top, like /data/prerolls on Linux or Docker, or D:\\Prerolls on Windows.");
  }
  if (text.split(/[\\/]/).includes("..")) return fail(`The ${what} path can't contain "..". Use the full path.`);
  return ok(text);
}

// ---------------------------------------------------------------------------
// Times and dates
// ---------------------------------------------------------------------------

/** "7:5" -> "07:05". 24-hour time with an optional am/pm. */
export function cleanTimeHHMM(value: string): Check {
  if (typeof value !== "string" || !value.trim()) return fail("Enter a time like 18:30.");
  const text = value.trim().toLowerCase().replace(/\./g, ":");
  const m = /^(\d{1,2})(?::(\d{1,2}))?\s*(am|pm)?$/.exec(text);
  if (!m) return fail("Enter a time like 18:30 or 6:30 pm.");
  let hour = Number(m[1]);
  const minute = Number(m[2] ?? 0);
  const ampm = m[3];
  if (ampm) {
    if (hour < 1 || hour > 12) return fail("With am or pm, the hour must be between 1 and 12.");
    hour = (hour % 12) + (ampm === "pm" ? 12 : 0);
  }
  if (hour > 23 || minute > 59) return fail("That time doesn't exist. Use hours 0-23 and minutes 0-59.");
  return ok(`${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`);
}

export function parseDate(value: string): Check {
  if (typeof value !== "string" || !value.trim()) return fail("Enter a date like 2026-12-24.");
  const text = value.trim().slice(0, 10);
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text);
  if (!m) return fail("Enter a date like 2026-12-24.");
  const [y, mo, d] = [Number(m[1]), Number(m[2]), Number(m[3])];
  const date = new Date(Date.UTC(y, mo - 1, d));
  if (date.getUTCFullYear() !== y || date.getUTCMonth() !== mo - 1 || date.getUTCDate() !== d || y < 1) {
    return fail("Enter a date like 2026-12-24.");
  }
  return ok(text);
}

/** Returns the message when `end` is before `start` (both ISO strings), else null. */
export function checkDateRange(start: string | null | undefined, end: string | null | undefined, startLabel = "start", endLabel = "end"): string | null {
  if (start && end && end < start) return `The ${endLabel} must be after the ${startLabel}.`;
  return null;
}

export function cleanHexColor(value: string): Check {
  if (typeof value !== "string" || !/^#?[0-9a-fA-F]{6}$/.test(value.trim())) {
    return fail("Pick a colour, or enter one like #3366FF.");
  }
  return ok(("#" + value.trim().replace(/^#/, "")).toUpperCase());
}

// ---------------------------------------------------------------------------
// Accounts (CONTRACTS.md §4)
// ---------------------------------------------------------------------------

export function cleanUsername(value: string): Check {
  const text = (value ?? "").trim().toLowerCase();
  if (!text) return fail("Enter a user name.");
  if (text.length < 3) return fail("Use at least 3 characters for the user name.");
  if (text.length > 32) return fail("Keep the user name to 32 characters or fewer.");
  if (!/^[a-z0-9][a-z0-9._-]*$/.test(text)) return fail("Use only letters, numbers, dots, dashes and underscores in the user name.");
  return ok(text);
}

// The same list as COMMON_PASSWORDS in main.py: the most common passwords of
// 8 characters or more. Nothing else is required (CONTRACTS.md §4).
const COMMON_PASSWORDS = new Set([
  "password", "12345678", "123456789", "1234567890", "password1", "password123",
  "qwerty123", "qwertyuiop", "iloveyou", "11111111", "00000000", "1q2w3e4r",
  "admin123", "87654321", "123123123", "abcd1234", "sunshine", "princess",
  "football", "baseball",
]);

export function checkPassword(value: string): Check {
  if (!value) return fail("Enter a password.");
  if (!value.trim()) return fail("The password can't be only spaces.");
  if (value.length < 8) return fail("Use at least 8 characters.");
  if (new TextEncoder().encode(value).length > 72) return fail("That password is too long. Keep it under 72 characters.");
  if (COMMON_PASSWORDS.has(value.trim().toLowerCase())) {
    return fail("That's one of the most common passwords, so it's easy to guess. Pick another.");
  }
  return ok(value);
}
