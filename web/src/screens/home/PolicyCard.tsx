import { Link } from "react-router";
import { useRunPolicy } from "@/api/queries";
import type { PolicySummary } from "@/api/types";
import { dateTime, plural } from "@/lib/format";
import { RUN_STATUS } from "@/lib/runLabels";
import { Button, Card, Tag } from "@/ui";

export function PolicyCard({ policy }: { policy: PolicySummary }) {
  const runNow = useRunPolicy();
  const current = policy.active_run ?? policy.last_run;
  const status = current ? RUN_STATUS[current.status] : null;
  const busy = !!policy.active_run;
  return (
    <Card className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-[17px] font-bold">{policy.name}</h3>
        <div className="flex gap-1.5">
          {policy.gate === "armed" && <Tag tone="violet">Safety check pending</Tag>}
          {!policy.enabled && <Tag tone="muted">Paused</Tag>}
          {status && <Tag tone={status.tone}>{status.label}</Tag>}
        </div>
      </div>
      {policy.active_run?.status === "running" && (
        <p className="text-[15px] font-semibold text-accent">
          {policy.active_run.dry_run
            ? "Safety check running…"
            : `${policy.active_run.downloaded} new so far`}
        </p>
      )}
      <p className="text-[14px] text-muted">
        {policy.enabled && policy.next_run_at
          ? `Next run ${dateTime(policy.next_run_at, policy.timezone)}`
          : "No scheduled runs"}
        {policy.last_success &&
          ` · last success ${plural(policy.last_success.downloaded, "new photo")}`}
      </p>
      <div className="flex gap-2 pt-1">
        <Button
          variant="secondary"
          busy={runNow.isPending}
          disabled={busy}
          onClick={() => runNow.mutate(policy.name)}
        >
          Run now
        </Button>
        {current && (
          <Link
            to={`/runs/${current.id}`}
            className="inline-flex min-h-11 items-center px-3 text-[15px] font-semibold text-muted"
          >
            Details
          </Link>
        )}
      </div>
      {runNow.error && <p className="text-[13px] text-red">{runNow.error.message}</p>}
    </Card>
  );
}
