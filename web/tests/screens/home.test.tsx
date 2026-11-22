import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { pol, run } from "../fixtures";
import { account, server } from "../msw";
import { renderAt } from "../render";

test("running policy shows live count", async () => {
  server.use(
    http.get("/api/policies", () =>
      HttpResponse.json([pol({ active_run: run({ id: "r2", status: "running", downloaded: 9 }) })])
    )
  );
  renderAt("/");
  expect(await screen.findByText("9 new so far")).toBeInTheDocument();
});

test("status card is red and the tab shows a badge when re-auth is needed", async () => {
  server.use(
    http.get("/api/account", () =>
      HttpResponse.json({ ...account, state: "needs_reauth", reason: "Session expired" })
    ),
    http.get("/api/policies", () => HttpResponse.json([pol()]))
  );
  renderAt("/");
  expect(await screen.findByText("iCloud needs you")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Re-authenticate" })).toHaveAttribute(
    "href",
    "/account/reauth"
  );
  expect(screen.getByLabelText("Needs you")).toBeInTheDocument();
});

test("run now triggers the policy", async () => {
  let called = false;
  server.use(
    http.get("/api/policies", () => HttpResponse.json([pol()])),
    http.post("/api/policies/icloud/run", () => {
      called = true;
      return HttpResponse.json(run({ id: "r3", status: "queued" }), { status: 202 });
    })
  );
  renderAt("/");
  await userEvent.click(await screen.findByRole("button", { name: "Run now" }));
  expect(called).toBe(true);
});

test("migration card dismisses", async () => {
  let notes = ["Your Apple sign-in moved to /data/icloud-session."];
  server.use(
    http.get("/api/account", () => HttpResponse.json({ ...account, migration_notes: notes })),
    http.post("/api/account/dismiss-notes", () => {
      notes = [];
      return HttpResponse.json({ ok: true });
    })
  );
  renderAt("/");
  expect(await screen.findByText(notes[0])).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Got it" }));
  expect(await screen.findByText("All good")).toBeInTheDocument();
  expect(screen.queryByText("What changed")).not.toBeInTheDocument();
});

test("last night card links to the run", async () => {
  server.use(http.get("/api/policies", () => HttpResponse.json([pol()])));
  renderAt("/");
  expect(await screen.findByText("12 new photos")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "View" })).toHaveAttribute("href", "/runs/r1");
});
