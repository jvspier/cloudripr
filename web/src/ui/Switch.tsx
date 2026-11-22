import * as RadixSwitch from "@radix-ui/react-switch";
import type { ReactNode } from "react";
import { useId } from "react";

export function Switch({
  label,
  hint,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  hint?: ReactNode;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  const id = useId();
  return (
    <div className="flex items-center justify-between gap-4 py-1">
      <label htmlFor={id} className="flex flex-col">
        <span className="text-[15px]">{label}</span>
        {hint && <span className="text-[13px] text-muted">{hint}</span>}
      </label>
      <RadixSwitch.Root
        id={id}
        checked={checked}
        onCheckedChange={onChange}
        disabled={disabled}
        className="relative h-7 w-12 shrink-0 rounded-full bg-line data-[state=checked]:bg-violet disabled:opacity-50"
      >
        <RadixSwitch.Thumb className="block size-6 translate-x-0.5 rounded-full bg-white shadow transition-transform data-[state=checked]:translate-x-[22px]" />
      </RadixSwitch.Root>
    </div>
  );
}
