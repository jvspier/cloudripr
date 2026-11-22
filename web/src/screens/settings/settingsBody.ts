import type { Settings } from "@/api/types";

export type SettingsBody = Omit<Settings, "smtp_password_set" | "email_last_error"> & {
  smtp_password: string | null;
};

/** PUT /api/settings replaces everything: start from the server copy, drop read-only keys. */
export function settingsBody(
  current: Settings,
  patch: Partial<Settings>,
  smtpPassword: string | null = null
): SettingsBody {
  const body: Partial<Settings> & { smtp_password: string | null } = {
    ...current,
    ...patch,
    smtp_password: smtpPassword,
  };
  delete body.smtp_password_set;
  delete body.email_last_error;
  return body as SettingsBody;
}
