import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useEvents, CONNECTION_GRACE_MS } from "@/api/events";
import { qk } from "@/api/queries";
import type { PolicySummary, Run } from "@/api/types";
import { FakeEventSource } from "../fakeEventSource";
import { account } from "../msw";
import { newQueryClient } from "../render";

afterEach(() => vi.useRealTimers());

const run = (over: Partial<Run> = {}): Run => ({
  id: "r1",
  policy: "icloud",
  trigger: "schedule",
  status: "running",
  started_at: "2026-11-22T02:00:00+00:00",
  ended_at: null,
  reason: null,
  exit_code: null,
  downloaded: 3,
  filter_kept: 0,
  filter_deleted: 0,
  dry_run: false,
  would_download: null,
  icloudpd_version: "1.32.3",
  log_path: null,
  ...over,
});

function setup() {
  const client = newQueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const hook = renderHook(() => useEvents(), { wrapper });
  return { client, hook, es: FakeEventSource.last! };
}

test("run event patches the policy's active run", () => {
  const { client, es } = setup();
  client.setQueryData(qk.policies, [
    { name: "icloud", active_run: run(), last_run: null },
  ] as unknown as PolicySummary[]);
  client.setQueryData(qk.run("r1"), { ...run(), file_count: 0, gate_review: null });
  act(() => es.emit("run", run({ downloaded: 9 })));
  const policies = client.getQueryData<PolicySummary[]>(qk.policies)!;
  expect(policies[0].active_run?.downloaded).toBe(9);
  expect(client.getQueryData<Run>(qk.run("r1"))?.downloaded).toBe(9);
});

test("account event merges into the cached account", () => {
  const { client, es } = setup();
  client.setQueryData(qk.account, account);
  act(() => es.emit("account", { ...account, state: "needs_reauth", migration_notes: undefined }));
  const cached = client.getQueryData<typeof account>(qk.account)!;
  expect(cached.state).toBe("needs_reauth");
  expect(cached.versions).toEqual(account.versions);
});

test("reconnect: error shows banner, hello clears it and refreshes account", async () => {
  vi.useFakeTimers();
  const { client, hook, es } = setup();
  act(() => es.emit("hello", { account, runs: [] }));
  expect(hook.result.current.connected).toBe(true);
  act(() => es.fail());
  expect(hook.result.current.connected).toBe(true); // short blips are ignored
  act(() => vi.advanceTimersByTime(CONNECTION_GRACE_MS + 10));
  expect(hook.result.current.connected).toBe(false);
  act(() => es.emit("hello", { account: { ...account, state: "needs_reauth" }, runs: [] }));
  vi.useRealTimers();
  await waitFor(() => expect(hook.result.current.connected).toBe(true));
  expect(client.getQueryData<typeof account>(qk.account)?.state).toBe("needs_reauth");
});

test("closes the stream on unmount", () => {
  const { hook, es } = setup();
  hook.unmount();
  expect(es.closed).toBe(true);
});

test("a run that finishes refetches its detail (gate review, file count)", () => {
  const { client, es } = setup();
  client.setQueryData(qk.run("r1"), { ...run(), file_count: 0, gate_review: null });
  act(() => es.emit("run", run({ status: "gate_blocked" })));
  expect(client.getQueryState(qk.run("r1"))?.isInvalidated).toBe(true);
});

test("a run event does not invent a detail entry without gate_review", () => {
  const { client, es } = setup();
  act(() => es.emit("run", run({ id: "r7", status: "running" })));
  expect(client.getQueryData(qk.run("r7"))).toBeUndefined();
});
