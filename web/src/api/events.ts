import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { qk } from "./queries";
import {
  ACTIVE_RUN_STATUSES,
  FINAL_ATTEMPT_STATES,
  type Account,
  type Attempt,
  type PolicySummary,
  type Run,
} from "./types";

/** Short drops (iPhone backgrounding, proxy hiccups) don't flash the banner. */
export const CONNECTION_GRACE_MS = 3000;

function mergeAccount(client: QueryClient, account: Account) {
  client.setQueryData<Account>(
    qk.account,
    (old) => ({ ...old, ...stripUndefined(account) }) as Account
  );
}

function stripUndefined<T extends object>(obj: T): Partial<T> {
  return Object.fromEntries(Object.entries(obj).filter(([, v]) => v !== undefined)) as Partial<T>;
}

function applyRun(client: QueryClient, run: Run) {
  // Only patch a detail entry that exists: a bare event lacks gate_review and file_count.
  client.setQueryData(qk.run(run.id), (old: object | undefined) =>
    old ? { ...old, ...run } : old
  );
  client.setQueryData<PolicySummary[]>(qk.policies, (old) =>
    old?.map((p) =>
      p.name !== run.policy
        ? p
        : {
            ...p,
            active_run: p.active_run?.id === run.id ? run : p.active_run,
            last_run: p.last_run?.id === run.id ? run : p.last_run,
          }
    )
  );
  if (!ACTIVE_RUN_STATUSES.includes(run.status)) {
    void client.invalidateQueries({ queryKey: qk.policies });
    void client.invalidateQueries({ queryKey: ["runs"] });
    void client.invalidateQueries({ queryKey: qk.run(run.id) });
  }
}

function applyAttempt(client: QueryClient, attempt: Attempt) {
  client.setQueryData(qk.attempt, { attempt });
  if (FINAL_ATTEMPT_STATES.includes(attempt.state)) {
    void client.invalidateQueries({ queryKey: qk.account });
    void client.invalidateQueries({ queryKey: qk.attempts });
  }
}

/** One EventSource on /api/events that keeps the query cache live. */
export function useEvents(): { connected: boolean } {
  const client = useQueryClient();
  const [connected, setConnected] = useState(true);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const es = new EventSource("/api/events");
    const clearTimer = () => {
      if (timer.current) clearTimeout(timer.current);
      timer.current = null;
    };
    const on = <T>(type: string, fn: (data: T) => void) =>
      es.addEventListener(type, (e: MessageEvent) => fn(JSON.parse(e.data) as T));

    on<{ account: Account; runs: Run[] }>("hello", ({ account }) => {
      clearTimer();
      setConnected(true);
      mergeAccount(client, account);
      void client.invalidateQueries({ queryKey: qk.policies });
      void client.invalidateQueries({ queryKey: qk.attempt });
    });
    on<Account>("account", (a) => mergeAccount(client, a));
    on<Attempt>("reauth", (a) => applyAttempt(client, a));
    on<Run>("run", (r) => applyRun(client, r));
    es.onerror = () => {
      if (!timer.current) {
        timer.current = setTimeout(() => setConnected(false), CONNECTION_GRACE_MS);
      }
    };
    return () => {
      clearTimer();
      es.close();
    };
  }, [client]);

  return { connected };
}
