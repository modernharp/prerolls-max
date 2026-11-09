// Small controls: tooltip, labelled switch, toggle chips.
import * as RTooltip from "@radix-ui/react-tooltip";
import * as RSwitch from "@radix-ui/react-switch";
import { useId, type ReactNode } from "react";

export function Tip({ content, children }: { content: ReactNode; children: ReactNode }) {
  return (
    <RTooltip.Root delayDuration={200}>
      <RTooltip.Trigger asChild>{children}</RTooltip.Trigger>
      <RTooltip.Portal>
        <RTooltip.Content className="tooltip" sideOffset={6}>
          {content}
          <RTooltip.Arrow className="tooltip-arrow" />
        </RTooltip.Content>
      </RTooltip.Portal>
    </RTooltip.Root>
  );
}

interface SwitchRowProps {
  label: ReactNode;
  description?: ReactNode;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}

export function SwitchRow({ label, description, checked, onChange, disabled }: SwitchRowProps) {
  const id = useId();
  return (
    <div className="switch-row">
      <div className="grow">
        <label htmlFor={id} className="field-label">
          {label}
        </label>
        {description && (
          <p id={`${id}-d`} className="field-help">
            {description}
          </p>
        )}
      </div>
      <RSwitch.Root
        id={id}
        className="switch"
        checked={checked}
        onCheckedChange={onChange}
        disabled={disabled}
        aria-describedby={description ? `${id}-d` : undefined}
      >
        <RSwitch.Thumb className="switch-thumb" />
      </RSwitch.Root>
    </div>
  );
}

interface ChipsProps<T extends string | number> {
  options: { value: T; label: string }[];
  selected: T[];
  onChange: (next: T[]) => void;
  describedBy?: string;
}

export function ToggleChips<T extends string | number>({ options, selected, onChange, describedBy }: ChipsProps<T>) {
  const toggle = (value: T) =>
    onChange(selected.includes(value) ? selected.filter((v) => v !== value) : [...selected, value]);
  return (
    <div className="chips" aria-describedby={describedBy}>
      {options.map((o) => (
        <button
          key={String(o.value)}
          type="button"
          className="chip"
          aria-pressed={selected.includes(o.value)}
          onClick={() => toggle(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
