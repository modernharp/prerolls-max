// Small formatting helpers for numbers, sizes and dates people read.

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return "";
  const total = Math.round(seconds);
  if (total < 60) return `${total} sec`;
  const m = Math.floor(total / 60);
  const s = total % 60;
  return s ? `${m} min ${s} sec` : `${m} min`;
}

export function formatSize(bytes: number | null | undefined): string {
  if (!bytes || bytes < 0) return "";
  const units = ["bytes", "KB", "MB", "GB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value < 10 && unit > 0 ? value.toFixed(1) : Math.round(value)} ${units[unit]}`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

/** "2026-10-01..." -> "Oct 1" (or "Oct 1, 2026" with year). Reads the wall-clock date as written. */
export function formatDay(iso: string | null | undefined, withYear = false): string {
  if (!iso) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return "";
  const month = MONTHS[Number(m[2]) - 1] ?? "";
  const day = Number(m[3]);
  return withYear ? `${month} ${day}, ${Number(m[1])}` : `${month} ${day}`;
}

/** "18:30" -> "6:30 pm" */
export function formatTime(hhmm: string | null | undefined): string {
  if (!hhmm) return "";
  const m = /^(\d{1,2}):(\d{2})/.exec(hhmm);
  if (!m) return hhmm;
  const h = Number(m[1]);
  const suffix = h >= 12 ? "pm" : "am";
  const h12 = h % 12 === 0 ? 12 : h % 12;
  return m[2] === "00" ? `${h12} ${suffix}` : `${h12}:${m[2]} ${suffix}`;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`;
}

export function videoName(p: { display_name: string | null; filename: string }): string {
  if (p.display_name) return p.display_name;
  return p.filename.replace(/\.[a-z0-9]{2,4}$/i, "");
}
