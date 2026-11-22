import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

export const account = {
  apple_id: "me@example.com",
  domain: "com",
  has_password: true,
  state: "ok",
  since: null,
  last_verified_at: "2026-11-22T18:00:00+00:00",
  reason: null,
  attempt: null,
  busy_with: null,
  migration_notes: [],
  versions: { app: "2.0.0", icloudpd: "1.32.3" },
  has_session: true,
  email_last_error: null,
};

export const defaultHandlers = [
  http.get("/api/auth/status", () =>
    HttpResponse.json({ authenticated: true, setup_required: false })
  ),
  http.get("/api/account", () => HttpResponse.json(account)),
  http.get("/api/account/reauth", () => HttpResponse.json({ attempt: null })),
  http.get("/api/account/attempts", () => HttpResponse.json([])),
  http.get("/api/policies", () => HttpResponse.json([])),
  http.get("/api/runs", () => HttpResponse.json([])),
  http.get("/api/settings", () =>
    HttpResponse.json({
      email: {
        to: null,
        smtp_host: "smtp.gmail.com",
        smtp_port: 587,
        smtp_user: null,
        smtp_security: "starttls",
        extra_urls: [],
        on_failure: true,
        on_success: false,
        app_url: null,
      },
      retention_runs: 30,
      idle_timeout_minutes: 30,
      session_check_time: "19:00",
      gate_threshold: 100,
      smtp_password_set: false,
      email_last_error: null,
    })
  ),
];

export const server = setupServer(...defaultHandlers);
