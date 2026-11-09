// Shown under a schedule, playlist or rule whose name another one also has.
// Only old databases (NeXroll imports) can hold such pairs: saving a taken
// name is refused, so this nudges people to rename one.
import { Info } from "lucide-react";
import type { NamedKind } from "../lib/names";

export function SharedNameHint({ kind }: { kind: NamedKind }) {
  return (
    <p className="muted small shared-name-hint">
      <Info size={14} aria-hidden="true" /> Another {kind} has this name too. Rename one so you can tell them apart.
    </p>
  );
}
