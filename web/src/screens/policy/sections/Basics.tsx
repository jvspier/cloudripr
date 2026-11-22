import { Field, inputClass, Switch } from "@/ui";
import { Section, type SectionProps } from "./common";

export function Basics({
  draft,
  set,
  fieldError,
  isNew,
  onName,
}: SectionProps & { isNew: boolean; onName: (n: string) => void }) {
  return (
    <Section title="Basics">
      {isNew && (
        <Field
          label="Name"
          hint="Letters, digits, - and _. Can't be changed later."
          error={fieldError("name")}
        >
          <input
            className={inputClass}
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            value={draft.name}
            onChange={(e) => onName(e.target.value)}
          />
        </Field>
      )}
      <Switch
        label="Enabled"
        hint="Run on schedule"
        checked={draft.enabled}
        onChange={(enabled) => set({ enabled })}
      />
    </Section>
  );
}
