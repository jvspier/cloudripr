import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { apiText } from "@/api/client";
import { useAccount, useAttempts, useSaveAccount } from "@/api/queries";
import type { Account } from "@/api/types";
import { dateTime } from "@/lib/format";
import { Button, Field, inputClass, Section, Sheet, Tag } from "@/ui";

const STATE: Record<Account["state"], { label: string; tone: "ok" | "red" | "violet" | "muted" }> =
  {
    ok: { label: "Signed in", tone: "ok" },
    needs_reauth: { label: "Needs sign-in", tone: "red" },
    reauthenticating: { label: "Signing in…", tone: "violet" },
    unknown: { label: "Not checked yet", tone: "muted" },
  };

function AttemptLog({ id, onClose }: { id: string | null; onClose: () => void }) {
  const log = useQuery({
    queryKey: ["attempt-log", id],
    queryFn: () => apiText(`/account/attempts/${encodeURIComponent(id ?? "")}/log`),
    enabled: !!id,
  });
  const text = log.error ? log.error.message : (log.data ?? null);
  return (
    <Sheet open={!!id} onOpenChange={(v) => !v && onClose()} title="Sign-in log">
      <pre className="whitespace-pre-wrap break-all font-mono text-[12px]">
        {text ?? "Loading…"}
      </pre>
    </Sheet>
  );
}

export function AccountSection() {
  const account = useAccount();
  const attempts = useAttempts();
  const save = useSaveAccount();
  const [appleId, setAppleId] = useState("");
  const [domain, setDomain] = useState<"com" | "cn">("com");
  const [password, setPassword] = useState("");
  const [saved, setSaved] = useState(false);
  const [logId, setLogId] = useState<string | null>(null);

  // Follow the server's Apple ID and domain (first load, after a save).
  const server = account.data ? `${account.data.apple_id ?? ""}|${account.data.domain}` : null;
  const [synced, setSynced] = useState<string | null>(null);
  if (account.data && server !== synced) {
    setSynced(server);
    setAppleId(account.data.apple_id ?? "");
    setDomain(account.data.domain);
  }

  const a = account.data;
  const onSave = () =>
    save.mutate(
      { apple_id: appleId.trim(), domain, ...(password ? { password } : {}) },
      {
        onSuccess: () => {
          setPassword("");
          setSaved(true);
        },
      }
    );

  return (
    <Section title="Account" anchor="account">
      {a && (
        <div className="flex items-center justify-between gap-2">
          <Tag tone={STATE[a.state].tone}>{STATE[a.state].label}</Tag>
          <Link to="/account/reauth" className="text-[15px] font-semibold text-accent">
            Re-authenticate
          </Link>
        </div>
      )}
      <Field
        label="Apple ID"
        error={
          save.error && (save.error as { field?: string }).field === "apple_id"
            ? save.error.message
            : undefined
        }
      >
        <input
          type="email"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          autoComplete="username"
          className={inputClass}
          value={appleId}
          onChange={(e) => {
            setSaved(false);
            setAppleId(e.target.value);
          }}
        />
      </Field>
      <Field label="Region">
        <select
          className={inputClass}
          value={domain}
          onChange={(e) => setDomain(e.target.value as "com" | "cn")}
        >
          <option value="com">Worldwide (icloud.com)</option>
          <option value="cn">China mainland (icloud.com.cn)</option>
        </select>
      </Field>
      <Field label="Apple ID password" hint="Stored on the server; never shown again.">
        <input
          type="password"
          autoComplete="current-password"
          className={inputClass}
          placeholder={a?.has_password ? "•••••• saved" : ""}
          value={password}
          onChange={(e) => {
            setSaved(false);
            setPassword(e.target.value);
          }}
        />
      </Field>
      {save.error && (save.error as { field?: string }).field !== "apple_id" && (
        <p className="text-[14px] text-red">{save.error.message}</p>
      )}
      <div className="flex items-center gap-2">
        <Button busy={save.isPending} disabled={!appleId.trim()} onClick={onSave}>
          Save account
        </Button>
        {saved && (
          <span className="text-[14px] font-semibold text-green-dark dark:text-green">Saved</span>
        )}
      </div>
      <div>
        <h3 className="mb-1 text-[13px] font-semibold text-muted">Sign-in history</h3>
        {attempts.data?.length === 0 && <p className="text-[14px] text-muted">No sign-ins yet.</p>}
        <ul className="flex flex-col">
          {attempts.data?.map((t) => (
            <li
              key={t.id}
              className="flex items-center gap-2 border-t border-line py-2 text-[14px]"
            >
              <span className="flex-1">{dateTime(t.started_at)}</span>
              <Tag tone={t.outcome === "succeeded" ? "ok" : t.outcome ? "red" : "violet"}>
                {t.outcome ?? "in progress"}
              </Tag>
              {t.log_path && (
                <Button variant="ghost" className="min-h-8 px-2" onClick={() => setLogId(t.id)}>
                  Log
                </Button>
              )}
            </li>
          ))}
        </ul>
      </div>
      <AttemptLog id={logId} onClose={() => setLogId(null)} />
    </Section>
  );
}
