import { homeStatus } from "@/lib/status";
import { acct, pol, run } from "../fixtures";

test("needs_reauth wins over everything", () => {
  expect(
    homeStatus(
      acct({ state: "needs_reauth", reason: "Session expired" }),
      [pol({ gate: "blocked", gate_review: { run_id: "r9", count: 412, sample: [] } })],
      false
    )
  ).toMatchObject({
    tone: "red",
    title: "iCloud needs you",
    detail: "Session expired",
    action: { to: "/account/reauth" },
  });
});

test("needs_reauth without a reason has a default", () => {
  expect(homeStatus(acct({ state: "needs_reauth", reason: null }), [], false).detail).toBe(
    "Apple wants you to sign in again."
  );
});

test("gate blocked points at the blocked run", () => {
  const s = homeStatus(
    acct(),
    [pol({ gate: "blocked", gate_review: { run_id: "r9", count: 412, sample: [] } })],
    false
  );
  expect(s).toMatchObject({
    tone: "red",
    title: "Check before downloading",
    action: { to: "/runs/r9" },
  });
  expect(s.detail).toContain("412");
  expect(s.detail).toContain("icloud");
});

test("failed last run shows its reason", () => {
  const s = homeStatus(
    acct(),
    [pol({ last_run: run({ id: "r5", status: "failed", reason: "No activity for 30 min" }) })],
    false
  );
  expect(s).toMatchObject({
    tone: "red",
    title: "Last backup didn't finish",
    detail: "No activity for 30 min",
    action: { to: "/runs/r5" },
  });
});

test("skipped last run is red too", () => {
  expect(
    homeStatus(acct(), [pol({ last_run: run({ status: "skipped", reason: "x" }) })], false).tone
  ).toBe("red");
});

test("missing Apple ID asks for setup", () => {
  expect(homeStatus(acct({ apple_id: null }), [], false)).toMatchObject({
    tone: "red",
    title: "Set up your Apple ID",
    action: { to: "/settings" },
  });
});

test("just re-authenticated is green", () => {
  expect(homeStatus(acct(), [pol()], true)).toMatchObject({ tone: "green", title: "All set" });
});

test("all good when ok and nothing pending", () => {
  const s = homeStatus(acct({ state: "ok" }), [pol()], false);
  expect(s.tone).toBe("violet");
  expect(s.title).toBe("All good");
});

test("unknown state waits for the first check", () => {
  expect(homeStatus(acct({ state: "unknown", last_verified_at: null }), [], false).detail).toBe(
    "Waiting for the first check"
  );
});

test("no Apple session yet asks to sign in", () => {
  expect(homeStatus(acct({ state: "unknown", has_session: false }), [pol()], false)).toMatchObject({
    tone: "red",
    title: "Sign in to iCloud",
    action: { to: "/account/reauth" },
  });
});

test("missing Apple ID still comes before signing in", () => {
  expect(homeStatus(acct({ apple_id: null, has_session: false }), [], false).title).toBe(
    "Set up your Apple ID"
  );
});
