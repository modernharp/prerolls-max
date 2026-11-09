// One name per schedule, playlist and rule. Mirrors backend/unique_names.py:
// case and extra spaces don't count, and the message is the server's.

export type NamedKind = "schedule" | "playlist" | "rule";

interface Named {
  id: number;
  name: string;
}

export const nameKey = (name: string | null | undefined) => (name ?? "").split(/\s+/).filter(Boolean).join(" ").toLowerCase();

/** The other item that already has this name, if any. */
export function nameTakenBy<T extends Named>(items: readonly T[] | undefined, name: string, excludeId?: number): T | undefined {
  const key = nameKey(name);
  if (!key) return undefined;
  return items?.find((item) => item.id !== excludeId && nameKey(item.name) === key);
}

export const nameTakenMessage = (kind: NamedKind, existing: string) =>
  `There's already a ${kind} called '${existing.trim()}'. Pick another name.`;

/** The message for a name another item has, or undefined when it's free. */
export function checkNameFree<T extends Named>(kind: NamedKind, items: readonly T[] | undefined, name: string, excludeId?: number, currentName?: string) {
  // An item an old database already holds twice can keep its own name.
  if (currentName !== undefined && nameKey(currentName) === nameKey(name)) return undefined;
  const taken = nameTakenBy(items, name, excludeId);
  return taken ? nameTakenMessage(kind, taken.name) : undefined;
}

/** Ids of items whose name another item also has (old NeXroll databases). */
export function sharedNameIds(items: readonly Named[] | undefined): Set<number> {
  const groups = new Map<string, number[]>();
  for (const item of items ?? []) {
    const key = nameKey(item.name);
    groups.set(key, [...(groups.get(key) ?? []), item.id]);
  }
  return new Set([...groups.values()].filter((ids) => ids.length > 1).flat());
}
