import { useState } from "react";
import { useAccount, useLogout, useSaveSettings, useSettings } from "@/api/queries";
import type { Settings } from "@/api/types";
import { Button, Field, inputClass, Section } from "@/ui";
import { getThemePref, setThemePref, type ThemePref } from "@/lib/theme";
import { settingsBody } from "./settingsBody";

const THEMES: [ThemePref, string][] = [
  ["auto", "Automatic"],
  ["light", "Light"],
  ["dark", "Dark"],
];

/** Applies at once and is remembered on this device only. */
function ThemeChoice() {
  const [pref, setPref] = useState<ThemePref>(getThemePref);
  return (
    <Field label="Appearance" hint="Automatic follows this device. Saved on this device only.">
      <div role="radiogroup" aria-label="Appearance" className="flex rounded-full bg-line p-1">
        {THEMES.map(([value, label]) => (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={pref === value}
            onClick={() => {
              setPref(value);
              setThemePref(value);
            }}
            className={`min-h-10 flex-1 rounded-full text-[15px] font-semibold ${
              pref === value ? "bg-card text-text shadow-sm" : "text-muted"
            }`}
          >
            {label}
          </button>
        ))}
      </div>
    </Field>
  );
}

type AppFields = Pick<
  Settings,
  "session_check_time" | "idle_timeout_minutes" | "gate_threshold" | "retention_runs"
>;

export function AppSection() {
  const settings = useSettings();
  const account = useAccount();
  const save = useSaveSettings();
  const logout = useLogout();
  const [draft, setDraft] = useState<AppFields | null>(null);
  const [saved, setSaved] = useState(false);

  if (settings.data && !draft) {
    const { session_check_time, idle_timeout_minutes, gate_threshold, retention_runs } =
      settings.data;
    setDraft({ session_check_time, idle_timeout_minutes, gate_threshold, retention_runs });
  }

  const set = (patch: Partial<AppFields>) => {
    setSaved(false);
    setDraft((d) => (d ? { ...d, ...patch } : d));
  };
  const num = (
    key: Exclude<keyof AppFields, "session_check_time">,
    label: string,
    hint?: string
  ) => (
    <Field label={label} hint={hint}>
      <input
        type="number"
        inputMode="numeric"
        min={key === "gate_threshold" ? 0 : 1}
        className={inputClass}
        value={draft?.[key] ?? ""}
        onChange={(e) => set({ [key]: Number(e.target.value) })}
      />
    </Field>
  );
  const versions = account.data?.versions;

  return (
    <Section title="App" anchor="app">
      <ThemeChoice />
      {draft && (
        <>
          <Field
            label="Daily sign-in check"
            hint="Checks your Apple sign-in so you hear about it before the night. Empty turns it off."
          >
            <input
              type="time"
              className={inputClass}
              value={draft.session_check_time}
              onChange={(e) => set({ session_check_time: e.target.value })}
            />
          </Field>
          {num("idle_timeout_minutes", "Stop a backup after this many minutes without activity")}
          {num(
            "gate_threshold",
            "Safety check limit",
            "Ask before downloading more files than this after a change"
          )}
          {num("retention_runs", "Runs to keep per policy")}
          {save.error && <p className="text-[14px] text-red">{save.error.message}</p>}
          <div className="flex items-center gap-2">
            <Button
              busy={save.isPending}
              onClick={() =>
                save.mutate(settingsBody(settings.data!, draft), {
                  onSuccess: () => setSaved(true),
                })
              }
            >
              Save app settings
            </Button>
            {saved && (
              <span className="text-[14px] font-semibold text-green-dark dark:text-green">
                Saved
              </span>
            )}
          </div>
        </>
      )}
      {versions && (
        <p className="text-[13px] text-muted">
          App {versions.app} · icloudpd {versions.icloudpd}
        </p>
      )}
      <Button
        variant="secondary"
        className="self-start"
        busy={logout.isPending}
        onClick={() => logout.mutate()}
      >
        Log out
      </Button>
    </Section>
  );
}
