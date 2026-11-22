import { NumberField, Section, type SectionProps } from "./common";

export function Safety({ draft, set, fieldError }: SectionProps) {
  return (
    <Section title="Safety check">
      <NumberField
        label="Ask me first when more files than this would download"
        hint="Empty uses the default from Settings → App"
        value={draft.gate_threshold}
        onChange={(v) => set({ gate_threshold: v ?? null })}
        error={fieldError("gate_threshold")}
      />
    </Section>
  );
}
