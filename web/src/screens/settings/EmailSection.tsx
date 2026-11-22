import { useState } from "react";
import { useSaveSettings, useSettings, useTestEmail } from "@/api/queries";
import type { EmailSettings } from "@/api/types";
import { Button, Field, inputClass, Section, Switch } from "@/ui";
import { settingsBody } from "./settingsBody";

export function EmailSection() {
  const settings = useSettings();
  const save = useSaveSettings();
  const test = useTestEmail();
  const [email, setEmail] = useState<EmailSettings | null>(null);
  const [password, setPassword] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  if (settings.data && !email) {
    const e = settings.data.email;
    setEmail({ ...e, app_url: e.app_url || window.location.origin });
  }

  if (!settings.data || !email) return <Section title="Email alerts">…</Section>;
  const set = (patch: Partial<EmailSettings>) => {
    setSaved(false);
    setEmail({ ...email, ...patch });
  };
  const text = (key: "to" | "smtp_host" | "smtp_user" | "app_url") => ({
    value: email[key] ?? "",
    onChange: (e: { target: { value: string } }) => set({ [key]: e.target.value || null }),
  });

  const onSave = () =>
    save.mutate(settingsBody(settings.data!, { email }, password), {
      onSuccess: () => {
        setPassword(null);
        setSaved(true);
      },
    });

  return (
    <Section title="Email alerts" anchor="email">
      <Field label="Send alerts to">
        <input
          type="email"
          autoCapitalize="none"
          autoCorrect="off"
          className={inputClass}
          {...text("to")}
        />
      </Field>
      <Button
        variant="secondary"
        className="self-start"
        onClick={() =>
          set({ smtp_host: "smtp.gmail.com", smtp_port: 587, smtp_security: "starttls" })
        }
      >
        Use Gmail
      </Button>
      <Field label="SMTP server">
        <input
          autoCapitalize="none"
          autoCorrect="off"
          className={inputClass}
          {...text("smtp_host")}
          value={email.smtp_host}
        />
      </Field>
      <div className="flex gap-3">
        <div className="w-28">
          <Field label="Port">
            <input
              type="number"
              inputMode="numeric"
              className={inputClass}
              value={email.smtp_port}
              onChange={(e) => set({ smtp_port: Number(e.target.value) })}
            />
          </Field>
        </div>
        <div className="flex-1">
          <Field label="Security">
            <select
              className={inputClass}
              value={email.smtp_security}
              onChange={(e) =>
                set({ smtp_security: e.target.value as EmailSettings["smtp_security"] })
              }
            >
              <option value="starttls">STARTTLS</option>
              <option value="ssl">SSL/TLS</option>
              <option value="none">None</option>
            </select>
          </Field>
        </div>
      </div>
      <Field label="SMTP user">
        <input
          autoCapitalize="none"
          autoCorrect="off"
          className={inputClass}
          {...text("smtp_user")}
        />
      </Field>
      <Field
        label="SMTP password"
        hint={
          email.smtp_host === "smtp.gmail.com"
            ? "Use an app password from myaccount.google.com/apppasswords"
            : undefined
        }
      >
        <input
          type="password"
          autoComplete="new-password"
          className={inputClass}
          placeholder={settings.data.smtp_password_set && password === null ? "•••••• saved" : ""}
          value={password ?? ""}
          onChange={(e) => {
            setSaved(false);
            setPassword(e.target.value === "" ? null : e.target.value);
          }}
        />
      </Field>
      {settings.data.smtp_password_set && password === null && (
        <button
          type="button"
          className="self-start text-[14px] text-red"
          onClick={() => setPassword("")}
        >
          Remove saved password
        </button>
      )}
      {password === "" && (
        <p className="text-[14px] text-muted">The saved password is removed when you save.</p>
      )}
      <Switch
        label="Email me when a backup fails"
        checked={email.on_failure}
        onChange={(v) => set({ on_failure: v })}
      />
      <Switch
        label="Email me when a backup succeeds"
        checked={email.on_success}
        onChange={(v) => set({ on_success: v })}
      />
      <Field
        label="Link in emails"
        hint="The address you open this app with, e.g. your Tailscale name"
      >
        <input
          type="url"
          autoCapitalize="none"
          autoCorrect="off"
          className={inputClass}
          {...text("app_url")}
        />
      </Field>
      <details>
        <summary className="cursor-pointer text-[14px] font-semibold text-accent">Advanced</summary>
        <div className="mt-3">
          <Field label="Extra Apprise URLs" hint="One per line">
            <textarea
              rows={3}
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              className={inputClass}
              value={email.extra_urls.join("\n")}
              onChange={(e) => set({ extra_urls: e.target.value.split("\n") })}
            />
          </Field>
        </div>
      </details>
      {settings.data.email_last_error && (
        <p className="text-[14px] text-red">Last email failed: {settings.data.email_last_error}</p>
      )}
      {save.error && <p className="text-[14px] text-red">{save.error.message}</p>}
      <div className="flex flex-wrap items-center gap-2">
        <Button
          busy={save.isPending}
          onClick={() => {
            setEmail({
              ...email,
              extra_urls: email.extra_urls.map((u) => u.trim()).filter(Boolean),
            });
            onSave();
          }}
        >
          Save email settings
        </Button>
        <Button variant="secondary" busy={test.isPending} onClick={() => test.mutate()}>
          Send test email
        </Button>
        {saved && (
          <span className="text-[14px] font-semibold text-green-dark dark:text-green">Saved</span>
        )}
      </div>
      {test.data && (
        <p
          className={`text-[14px] ${test.data.ok ? "text-green-dark dark:text-green" : "text-red"}`}
        >
          {test.data.ok ? "Test email sent." : (test.data.error ?? "Sending failed.")}
        </p>
      )}
      {test.error && <p className="text-[14px] text-red">{test.error.message}</p>}
    </Section>
  );
}
