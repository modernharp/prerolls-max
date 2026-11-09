// Prerolls Max's clock vs this browser's (ported from utils/timezones.js).
// Schedules run on Prerolls Max's time zone; if it differs from the browser's,
// times on screen and when intros actually change won't match.

/** Minutes the zone is ahead of UTC at `date`, or null if the browser doesn't know it. */
export function zoneOffsetMinutes(timeZone: string | null | undefined, date = new Date()): number | null {
  if (!timeZone) return null;
  try {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone,
      hourCycle: "h23",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }).formatToParts(date);
    const get = (type: string) => Number(parts.find((p) => p.type === type)?.value);
    const asUtc = Date.UTC(get("year"), get("month") - 1, get("day"), get("hour") % 24, get("minute"), get("second"));
    const whole = Math.floor(date.getTime() / 1000) * 1000;
    const minutes = Math.round((asUtc - whole) / 60000);
    return Number.isFinite(minutes) ? minutes : null;
  } catch {
    return null;
  }
}

export function browserTimeZone(): string | null {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || null;
  } catch {
    return null;
  }
}

/** True when the zone is on a different offset from this browser right now. */
export function zonesDiffer(timeZone: string | null | undefined, date = new Date()): boolean {
  const offset = zoneOffsetMinutes(timeZone, date);
  return offset !== null && offset !== -date.getTimezoneOffset();
}

/** "6:45 PM" on the zone's clock. */
export function zoneTimeLabel(timeZone: string, date = new Date()): string {
  try {
    return date.toLocaleTimeString([], { timeZone, hour: "numeric", minute: "2-digit" });
  } catch {
    return "";
  }
}
