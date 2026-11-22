import { useState, type ReactNode } from "react";
export { Section } from "@/ui";
import type { Policy } from "@/api/types";
import { Field, inputClass } from "@/ui";

export interface SectionProps {
  draft: Policy;
  set: (patch: Partial<Policy>) => void;
  /** Set an [icloudpd] option; "", null and undefined remove the key. */
  setOpt: (key: string, value: unknown) => void;
  fieldError: (field: string) => string | undefined;
}

/** Integer input; empty means "not set". */
export function NumberField({
  label,
  hint,
  value,
  onChange,
  error,
  disabled,
}: {
  label: string;
  hint?: ReactNode;
  value: unknown;
  onChange: (v: number | undefined) => void;
  error?: string;
  disabled?: boolean;
}) {
  return (
    <Field label={label} hint={hint} error={error}>
      <input
        type="number"
        inputMode="numeric"
        min={0}
        className={inputClass}
        disabled={disabled}
        value={typeof value === "number" ? value : ""}
        onChange={(e) => onChange(e.target.value === "" ? undefined : Number(e.target.value))}
      />
    </Field>
  );
}

export function SelectField<T extends string>({
  label,
  value,
  options,
  onChange,
  disabled,
  error,
}: {
  label: string;
  value: T | null | undefined;
  options: readonly (readonly [T, string])[];
  onChange: (v: T) => void;
  disabled?: boolean;
  error?: string;
}) {
  return (
    <Field label={label} error={error}>
      <select
        className={inputClass}
        disabled={disabled}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value as T)}
      >
        {!value && <option value="">Default</option>}
        {options.map(([v, text]) => (
          <option key={v} value={v}>
            {text}
          </option>
        ))}
      </select>
    </Field>
  );
}

/** A string list edited one entry per line. Keeps the raw text while typing. */
export function ListField({
  label,
  hint,
  value,
  onChange,
  error,
}: {
  label: string;
  hint?: ReactNode;
  value: string[];
  onChange: (v: string[]) => void;
  error?: string;
}) {
  const joined = value.join("\n");
  const [raw, setRaw] = useState(joined);
  const [prev, setPrev] = useState(joined);
  if (joined !== prev) {
    // Follow outside changes (e.g. after a save) without fighting the user's typing.
    setPrev(joined);
    setRaw((cur) => (toList(cur).join("\n") === joined ? cur : joined));
  }
  return (
    <Field label={label} hint={hint} error={error}>
      <textarea
        rows={3}
        className={inputClass}
        autoCapitalize="none"
        autoCorrect="off"
        spellCheck={false}
        value={raw}
        onChange={(e) => {
          setRaw(e.target.value);
          onChange(toList(e.target.value));
        }}
      />
    </Field>
  );
}

const toList = (text: string) =>
  text
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
