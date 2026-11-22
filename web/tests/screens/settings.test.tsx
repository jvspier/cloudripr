import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { Settings } from "@/api/types";
import { server } from "../msw";
import { renderAt } from "../render";

const settings = (over: Partial<Settings> = {}): Settings => ({
  email: {
    to: "me@example.com",
    smtp_host: "smtp.example.com",
    smtp_port: 465,
    smtp_user: "me",
    smtp_security: "ssl",
    extra_urls: [],
    on_failure: true,
    on_success: false,
    app_url: "http://nas.tail1234.ts.net:5000",
  },
  retention_runs: 30,
  idle_timeout_minutes: 30,
  session_check_time: "19:00",
  gate_threshold: 100,
  smtp_password_set: true,
  email_last_error: null,
  ...over,
});

function serve(s = settings()) {
  let put: Record<string, unknown> | null = null;
  server.use(
    http.get("/api/settings", () => HttpResponse.json(s)),
    http.put("/api/settings", async ({ request }) => {
      put = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json(s);
    })
  );
  return () => put;
}

const emailSection = async () => {
  await screen.findByRole("button", { name: "Save email settings" }); // loaded
  return within(screen.getByRole("region", { name: "Email alerts" }));
};

test("untouched SMTP password is sent as null", async () => {
  const put = serve();
  renderAt("/settings");
  const email = await emailSection();
  await userEvent.click(email.getByRole("button", { name: "Save email settings" }));
  await email.findByText("Saved");
  expect(put()!.smtp_password).toBeNull();
  expect(put()).not.toHaveProperty("smtp_password_set");
  expect(put()).not.toHaveProperty("email_last_error");
  expect(put()!.retention_runs).toBe(30);
});

test("typed SMTP password is sent", async () => {
  const put = serve();
  renderAt("/settings");
  const email = await emailSection();
  await userEvent.type(email.getByLabelText("SMTP password"), "app-pass");
  await userEvent.click(email.getByRole("button", { name: "Save email settings" }));
  await email.findByText("Saved");
  expect(put()!.smtp_password).toBe("app-pass");
});

test("Gmail preset fills host, port and security", async () => {
  const put = serve();
  renderAt("/settings");
  const email = await emailSection();
  await userEvent.click(email.getByRole("button", { name: "Use Gmail" }));
  expect(email.getByLabelText("SMTP server")).toHaveValue("smtp.gmail.com");
  expect(email.getByLabelText("Port")).toHaveValue(587);
  await userEvent.click(email.getByRole("button", { name: "Save email settings" }));
  await email.findByText("Saved");
  expect(put()!.email).toMatchObject({
    smtp_host: "smtp.gmail.com",
    smtp_port: 587,
    smtp_security: "starttls",
  });
});

test("link in emails is prefilled from the current origin", async () => {
  serve(settings({ email: { ...settings().email, app_url: null } }));
  renderAt("/settings");
  const email = await emailSection();
  expect(email.getByLabelText("Link in emails")).toHaveValue(window.location.origin);
});

test("test email shows the error message", async () => {
  serve();
  server.use(
    http.post("/api/settings/test-email", () =>
      HttpResponse.json({ ok: false, error: "535 auth failed" })
    )
  );
  renderAt("/settings");
  const email = await emailSection();
  await userEvent.click(email.getByRole("button", { name: "Send test email" }));
  expect(await email.findByText("535 auth failed")).toBeInTheDocument();
});

test("last email error is shown", async () => {
  serve(settings({ email_last_error: "2026-11-22T03:00:00 timeout" }));
  renderAt("/settings");
  const email = await emailSection();
  expect(email.getByText(/Last email failed: 2026-11-22T03:00:00 timeout/)).toBeInTheDocument();
});

test("account save omits password when not typed", async () => {
  serve();
  let body: unknown = null;
  server.use(
    http.put("/api/account", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({
        apple_id: "new@example.com",
        domain: "com",
        has_password: true,
        state: "ok",
      });
    })
  );
  renderAt("/settings");
  await waitFor(() => expect(screen.getByLabelText("Apple ID")).toHaveValue("me@example.com"));
  const account = within(screen.getByRole("region", { name: "Account" }));
  const id = account.getByLabelText("Apple ID");
  expect(id).toHaveAttribute("type", "email");
  expect(id).toHaveAttribute("autocapitalize", "none");
  await userEvent.clear(id);
  await userEvent.type(id, "new@example.com");
  await userEvent.click(account.getByRole("button", { name: "Save account" }));
  await account.findByText("Saved");
  expect(body).toEqual({ apple_id: "new@example.com", domain: "com" });
});

test("sign-in history lists attempts with outcome", async () => {
  serve();
  server.use(
    http.get("/api/account/attempts", () =>
      HttpResponse.json([
        {
          id: "a1",
          started_at: "2026-11-22T18:00:00+00:00",
          ended_at: "2026-11-22T18:01:00+00:00",
          outcome: "succeeded",
          log_path: "/data/auth/a1.log",
        },
      ])
    ),
    http.get("/api/account/attempts/a1/log", () =>
      HttpResponse.text("Two-factor authentication is required")
    )
  );
  renderAt("/settings");
  const account = within(await screen.findByRole("region", { name: "Account" }));
  expect(await account.findByText("succeeded")).toBeInTheDocument();
  await userEvent.click(account.getByRole("button", { name: "Log" }));
  expect(await screen.findByText("Two-factor authentication is required")).toBeInTheDocument();
});

test("app settings save with the same PUT and logout works", async () => {
  const put = serve();
  let loggedOut = false;
  server.use(
    http.post("/api/auth/logout", () => {
      loggedOut = true;
      return HttpResponse.json({ ok: true });
    })
  );
  renderAt("/settings");
  await screen.findByRole("button", { name: "Save app settings" });
  await screen.findByText(/icloudpd 1.32.3/);
  const app = within(screen.getByRole("region", { name: "App" }));
  const check = app.getByLabelText("Daily sign-in check");
  await userEvent.clear(check);
  await userEvent.click(app.getByRole("button", { name: "Save app settings" }));
  await app.findByText("Saved");
  expect(put()!.session_check_time).toBe("");
  expect(app.getByText(/icloudpd 1.32.3/)).toBeInTheDocument();
  await userEvent.click(app.getByRole("button", { name: "Log out" }));
  expect(loggedOut).toBe(true);
});

test("appearance applies at once and is remembered on this device", async () => {
  renderAt("/settings");
  const group = await screen.findByRole("radiogroup", { name: "Appearance" });
  expect(within(group).getByRole("radio", { name: "Automatic" })).toBeChecked();
  await userEvent.click(within(group).getByRole("radio", { name: "Dark" }));
  expect(document.documentElement.dataset.theme).toBe("dark");
  expect(localStorage.getItem("cloudripr.theme")).toBe("dark");
  await userEvent.click(within(group).getByRole("radio", { name: "Automatic" }));
  expect(localStorage.getItem("cloudripr.theme")).toBeNull();
  expect(within(group).getByRole("radio", { name: "Automatic" })).toBeChecked();
});
