import { cronFromNightly, nightlyFromCron } from "@/lib/schedule";
import { Field, inputClass } from "@/ui";
import { Section, type SectionProps } from "./common";

export function Schedule({ draft, set, fieldError }: SectionProps) {
  const nightly = nightlyFromCron(draft.cron);
  return (
    <Section title="Schedule">
      <Field
        label="Every night at"
        hint={nightly ? undefined : "Custom schedule — see Advanced."}
        error={nightly ? fieldError("cron") : undefined}
      >
        <input
          type="time"
          className={inputClass}
          value={nightly ?? ""}
          onChange={(e) => e.target.value && set({ cron: cronFromNightly(e.target.value) })}
        />
      </Field>
      <details open={!nightly || !!fieldError("timezone")}>
        <summary className="cursor-pointer text-[14px] font-semibold text-accent">Advanced</summary>
        <div className="mt-3 flex flex-col gap-4">
          <Field label="Cron" hint="minute hour day month weekday" error={fieldError("cron")}>
            <input
              className={`${inputClass} font-mono`}
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              value={draft.cron}
              onChange={(e) => set({ cron: e.target.value })}
            />
          </Field>
          <Field
            label="Timezone"
            hint="For example Europe/Amsterdam"
            error={fieldError("timezone")}
          >
            <input
              className={inputClass}
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              placeholder="Container default"
              value={draft.timezone ?? ""}
              onChange={(e) => set({ timezone: e.target.value || null })}
            />
          </Field>
        </div>
      </details>
    </Section>
  );
}
