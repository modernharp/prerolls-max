// A styled single-choice list (Radix Select) with a visible label.
import * as RSelect from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";
import type { ReactNode } from "react";
import { FieldShell } from "./Field";

export interface Option {
  value: string;
  label: string;
}

interface SelectProps {
  label: ReactNode;
  value: string;
  onChange: (value: string) => void;
  options: Option[];
  placeholder?: string;
  help?: ReactNode;
  error?: string;
  optional?: boolean;
  disabled?: boolean;
  id?: string;
}

export function Select({ label, value, onChange, options, placeholder = "Choose…", help, error, optional, disabled, id }: SelectProps) {
  return (
    <FieldShell label={label} help={help} error={error} optional={optional} id={id}>
      {(ids) => (
        <RSelect.Root value={value} onValueChange={onChange} disabled={disabled}>
          <RSelect.Trigger
            id={ids.id}
            className="select-trigger"
            aria-invalid={ids.invalid || undefined}
            aria-describedby={ids.describedBy}
          >
            <RSelect.Value placeholder={placeholder} />
            <RSelect.Icon>
              <ChevronDown size={18} aria-hidden="true" />
            </RSelect.Icon>
          </RSelect.Trigger>
          <RSelect.Portal>
            <RSelect.Content className="select-content" position="popper" sideOffset={4}>
              <RSelect.Viewport className="select-viewport">
                {options.map((option) => (
                  <RSelect.Item key={option.value} value={option.value} className="select-item">
                    <RSelect.ItemText>{option.label}</RSelect.ItemText>
                    <RSelect.ItemIndicator>
                      <Check size={16} aria-hidden="true" />
                    </RSelect.ItemIndicator>
                  </RSelect.Item>
                ))}
              </RSelect.Viewport>
            </RSelect.Content>
          </RSelect.Portal>
        </RSelect.Root>
      )}
    </FieldShell>
  );
}
