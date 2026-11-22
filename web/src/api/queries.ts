import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { api } from "./client";
import {
  FINAL_ATTEMPT_STATES,
  type Account,
  type Attempt,
  type AttemptRecord,
  type AuthStatus,
  type LibraryItem,
  type LibraryMonth,
  type LibraryRun,
  type LibrarySummary,
  type Policy,
  type PolicySummary,
  type Run,
  type RunDetail,
  type Settings,
} from "./types";

export const qk = {
  auth: ["auth"] as const,
  account: ["account"] as const,
  attempt: ["attempt"] as const,
  attempts: ["attempts"] as const,
  policies: ["policies"] as const,
  policy: (name: string) => ["policies", name] as const,
  runs: (policy?: string) => ["runs", policy ?? null] as const,
  run: (id: string) => ["run", id] as const,
  settings: ["settings"] as const,
  library: ["library"] as const,
};

type AttemptEnvelope = { attempt: Attempt | null };

// ---- queries ----

export const useLibrarySummary = () =>
  useQuery({
    queryKey: [...qk.library, "summary"],
    queryFn: () => api<LibrarySummary>("/library/summary"),
  });
export const useLibraryRuns = () =>
  useQuery({
    queryKey: [...qk.library, "runs"],
    queryFn: () => api<LibraryRun[]>("/library/runs"),
  });
export const useLibraryMonths = () =>
  useQuery({
    queryKey: [...qk.library, "months"],
    queryFn: () => api<LibraryMonth[]>("/library/months"),
  });
export const useLibraryItems = (filter: { month: string } | { run: string }) => {
  const params = new URLSearchParams(filter).toString();
  return useQuery({
    queryKey: [...qk.library, "items", params],
    queryFn: () => api<LibraryItem[]>(`/library/items?${params}`),
  });
};

export const useAuthStatus = () =>
  useQuery({ queryKey: qk.auth, queryFn: () => api<AuthStatus>("/auth/status"), retry: false });

export const useAccount = () =>
  useQuery({ queryKey: qk.account, queryFn: () => api<Account>("/account") });

/** Polls every 3 s while an attempt is in progress, so the screen never relies on SSE alone. */
export const useAttempt = () =>
  useQuery({
    queryKey: qk.attempt,
    queryFn: () => api<AttemptEnvelope>("/account/reauth"),
    refetchInterval: (q) => {
      const state = q.state.data?.attempt?.state;
      return state && !FINAL_ATTEMPT_STATES.includes(state) ? 3000 : false;
    },
  });

export const useAttempts = () =>
  useQuery({ queryKey: qk.attempts, queryFn: () => api<AttemptRecord[]>("/account/attempts") });

export const usePolicies = () =>
  useQuery({ queryKey: qk.policies, queryFn: () => api<PolicySummary[]>("/policies") });

export const usePolicy = (name: string | undefined) =>
  useQuery({
    queryKey: qk.policy(name ?? ""),
    queryFn: () => api<PolicySummary>(`/policies/${encodeURIComponent(name!)}`),
    enabled: !!name,
  });

export const useRuns = (policy?: string, limit = 30) =>
  useQuery({
    queryKey: [...qk.runs(policy), limit],
    queryFn: () =>
      api<Run[]>(`/runs?limit=${limit}${policy ? `&policy=${encodeURIComponent(policy)}` : ""}`),
  });

export const useRun = (id: string | undefined) =>
  useQuery({
    queryKey: qk.run(id ?? ""),
    queryFn: () => api<RunDetail>(`/runs/${encodeURIComponent(id!)}`),
    enabled: !!id,
    retry: false,
    refetchInterval: (q) => {
      const status = q.state.data?.status;
      return status === "queued" || status === "running" ? 3000 : false;
    },
  });

export const useSettings = () =>
  useQuery({ queryKey: qk.settings, queryFn: () => api<Settings>("/settings") });

// ---- mutations ----

function invalidate(client: QueryClient, ...keys: readonly (readonly unknown[])[]) {
  return Promise.all(keys.map((queryKey) => client.invalidateQueries({ queryKey })));
}

function useAction<TVars, TResult>(
  fn: (vars: TVars) => Promise<TResult>,
  after: (client: QueryClient, result: TResult, vars: TVars) => unknown
) {
  const client = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: (r, v) => after(client, r, v) });
}

export const useLogin = () =>
  useAction(
    (password: string) => api("/auth/login", { method: "POST", json: { password } }),
    (c) => c.resetQueries()
  );
export const useSetup = () =>
  useAction(
    (password: string) => api("/auth/setup", { method: "POST", json: { password } }),
    (c) => c.resetQueries()
  );
export const useLogout = () =>
  useAction(
    (_: void) => api("/auth/logout", { method: "POST" }),
    (c) => {
      c.clear();
      return c.invalidateQueries({ queryKey: qk.auth });
    }
  );

export const useSaveAccount = () =>
  useAction(
    (body: { apple_id?: string; domain?: "com" | "cn"; password?: string }) =>
      api<Account>("/account", { method: "PUT", json: body }),
    (c, data) => c.setQueryData(qk.account, data)
  );

const setAttempt = (c: QueryClient, attempt: Attempt | null) => {
  c.setQueryData<AttemptEnvelope>(qk.attempt, { attempt });
  return invalidate(c, qk.account);
};
export const useStartReauth = () =>
  useAction(
    (_: void) => api<Attempt>("/account/reauth", { method: "POST" }),
    (c, a) => setAttempt(c, a)
  );
export const useRestartReauth = () =>
  useAction(
    (_: void) => api<Attempt>("/account/reauth/restart", { method: "POST" }),
    (c, a) => setAttempt(c, a)
  );
export const useSubmitCode = () =>
  useAction(
    (code: string) =>
      api<AttemptEnvelope>("/account/reauth/code", { method: "POST", json: { code } }),
    (c, r) => c.setQueryData(qk.attempt, r)
  );
export const useRequestSms = () =>
  useAction(
    (index: string) =>
      api<AttemptEnvelope>("/account/reauth/sms", { method: "POST", json: { index } }),
    (c, r) => c.setQueryData(qk.attempt, r)
  );
export const useCancelReauth = () =>
  useAction(
    (_: void) => api("/account/reauth", { method: "DELETE" }),
    (c) => invalidate(c, qk.attempt, qk.account, qk.attempts)
  );
export const useDismissNotes = () =>
  useAction(
    (_: void) => api("/account/dismiss-notes", { method: "POST" }),
    (c) => invalidate(c, qk.account)
  );

export const useSavePolicy = () =>
  useAction(
    (body: Policy) =>
      api<PolicySummary>(`/policies/${encodeURIComponent(body.name)}`, {
        method: "PUT",
        json: body,
      }),
    (c, p) => {
      c.setQueryData(qk.policy(p.name), p);
      return invalidate(c, qk.policies);
    }
  );
export const useDeletePolicy = () =>
  useAction(
    (name: string) => api(`/policies/${encodeURIComponent(name)}`, { method: "DELETE" }),
    (c) => invalidate(c, qk.policies)
  );
export const useRunPolicy = () =>
  useAction(
    (name: string) => api<Run>(`/policies/${encodeURIComponent(name)}/run`, { method: "POST" }),
    (c) => invalidate(c, qk.policies, ["runs"])
  );
export const useUnlockPolicy = () =>
  useAction(
    ({ name, confirm }: { name: string; confirm: string }) =>
      api<PolicySummary>(`/policies/${encodeURIComponent(name)}/unlock`, {
        method: "POST",
        json: { confirm },
      }),
    (c, p) => {
      c.setQueryData(qk.policy(p.name), p);
      return invalidate(c, qk.policies);
    }
  );
export const useImportPolicies = () =>
  useAction(
    (toml: string) =>
      api<{ created: string[]; errors: { name: string | null; error: string }[] }>(
        "/policies/import",
        { method: "POST", body: toml, headers: { "Content-Type": "application/toml" } }
      ),
    (c) => invalidate(c, qk.policies)
  );

export const useStopRun = () =>
  useAction(
    (id: string) => api(`/runs/${encodeURIComponent(id)}/stop`, { method: "POST" }),
    (c, _r, id) => invalidate(c, qk.run(id), qk.policies)
  );
export const useApproveRun = () =>
  useAction(
    (id: string) => api<Run>(`/runs/${encodeURIComponent(id)}/approve`, { method: "POST" }),
    (c) => invalidate(c, qk.policies, ["runs"])
  );

export const useSaveSettings = () =>
  useAction(
    (
      body: Omit<Settings, "smtp_password_set" | "email_last_error"> & {
        smtp_password: string | null;
      }
    ) => api<Settings>("/settings", { method: "PUT", json: body }),
    (c, s) => c.setQueryData(qk.settings, s)
  );
export const useTestEmail = () =>
  useAction(
    (_: void) =>
      api<{ ok: boolean; error: string | null }>("/settings/test-email", { method: "POST" }),
    (c) => invalidate(c, qk.settings)
  );
