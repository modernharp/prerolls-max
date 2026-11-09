// Per-browser preferences: theme and the Advanced switch. Stored locally; if
// the browser blocks storage the app still works with the defaults.
import { useSyncExternalStore } from "react";

export type Theme = "system" | "light" | "dark";

interface Prefs {
  theme: Theme;
  advanced: boolean;
  /** Someone confirmed an intro played in a test (Home checklist). */
  testPlayed: boolean;
}

const KEY = "pmax.prefs";
const defaults: Prefs = { theme: "system", advanced: false, testPlayed: false };

function load(): Prefs {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return defaults;
    const parsed = JSON.parse(raw) as Partial<Prefs>;
    return {
      theme: parsed.theme === "light" || parsed.theme === "dark" ? parsed.theme : "system",
      advanced: parsed.advanced === true,
      testPlayed: parsed.testPlayed === true,
    };
  } catch {
    return defaults;
  }
}

let current: Prefs = typeof window === "undefined" ? defaults : load();
const listeners = new Set<() => void>();

function save(next: Prefs) {
  current = next;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // Storage blocked (private window): keep it for this visit only.
  }
  applyTheme();
  listeners.forEach((fn) => fn());
}

export function applyTheme() {
  const root = document.documentElement;
  if (current.theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", current.theme);
}

function subscribe(fn: () => void) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function usePrefs(): Prefs {
  return useSyncExternalStore(subscribe, () => current, () => current);
}

export function setTheme(theme: Theme) {
  save({ ...current, theme });
}

export function setAdvanced(advanced: boolean) {
  save({ ...current, advanced });
}

export function setTestPlayed(testPlayed: boolean) {
  save({ ...current, testPlayed });
}
