import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "../msw";
import { renderAt } from "../render";

test("setup_required shows Set a password and posts it", async () => {
  let authed = false;
  let posted: unknown = null;
  server.use(
    http.get("/api/auth/status", () =>
      HttpResponse.json({ authenticated: authed, setup_required: !authed })
    ),
    http.post("/api/auth/setup", async ({ request }) => {
      posted = await request.json();
      authed = true;
      return HttpResponse.json({ ok: true });
    })
  );
  renderAt("/");
  await userEvent.type(await screen.findByLabelText("New password"), "correct horse");
  await userEvent.type(screen.getByLabelText("Repeat password"), "correct horse");
  await userEvent.click(screen.getByRole("button", { name: "Set password" }));
  expect(posted).toEqual({ password: "correct horse" });
  expect(await screen.findByRole("navigation", { name: "Main" })).toBeInTheDocument();
});

test("setup refuses mismatched passwords", async () => {
  server.use(
    http.get("/api/auth/status", () =>
      HttpResponse.json({ authenticated: false, setup_required: true })
    )
  );
  renderAt("/");
  await userEvent.type(await screen.findByLabelText("New password"), "one");
  await userEvent.type(screen.getByLabelText("Repeat password"), "two");
  await userEvent.click(screen.getByRole("button", { name: "Set password" }));
  expect(await screen.findByText("The passwords don't match.")).toBeInTheDocument();
});

test("wrong password shows the server message", async () => {
  server.use(
    http.get("/api/auth/status", () =>
      HttpResponse.json({ authenticated: false, setup_required: false })
    ),
    http.post("/api/auth/login", () =>
      HttpResponse.json({ error: "Wrong password.", error_id: null, field: null }, { status: 401 })
    )
  );
  renderAt("/");
  await userEvent.type(await screen.findByLabelText("Password"), "nope");
  await userEvent.click(screen.getByRole("button", { name: "Log in" }));
  expect(await screen.findByText("Wrong password.")).toBeInTheDocument();
});

test("a 401 from any call returns to the login screen", async () => {
  let authed = true;
  server.use(
    http.get("/api/auth/status", () =>
      HttpResponse.json({ authenticated: authed, setup_required: false })
    ),
    http.get("/api/policies", () => {
      authed = false;
      return HttpResponse.json(
        { error: "Not authenticated", error_id: null, field: null },
        { status: 401 }
      );
    })
  );
  renderAt("/");
  expect(await screen.findByRole("button", { name: "Log in" })).toBeInTheDocument();
  expect(screen.queryByText(/no policies/i)).not.toBeInTheDocument();
});
