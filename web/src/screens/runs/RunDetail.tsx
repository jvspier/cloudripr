import { ChevronLeft } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { usePolicy, useRun, useSettings, useStopRun } from "@/api/queries";
import { ACTIVE_RUN_STATUSES } from "@/api/types";
import { dateTime, duration, plural } from "@/lib/format";
import { RUN_STATUS } from "@/lib/runLabels";
import { Button, Card, Page, Spinner, Tag } from "@/ui";
import { GateReview } from "./GateReview";
import { LogView } from "./LogView";

const TRIGGERS = {
  schedule: "Scheduled",
  manual: "Started by you",
  "catch-up": "Catch-up",
  gate: "After safety check",
};

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex-1 rounded-2xl bg-page p-3">
      <p className="text-[12px] font-semibold text-muted">{label}</p>
      <p className="text-[20px] font-bold">{value}</p>
    </div>
  );
}

export function RunDetail() {
  const { id } = useParams();
  const runQ = useRun(id);
  const run = runQ.data;
  const policy = usePolicy(run?.gate_review ? run.policy : undefined);
  const settings = useSettings();
  const stop = useStopRun();
  const [showLog, setShowLog] = useState(false);

  const back = (
    <Link to="/" aria-label="Back" className="-ml-2 p-2 text-muted">
      <ChevronLeft className="size-6" />
    </Link>
  );
  if (runQ.error) {
    return (
      <Page title="Run" back={back}>
        <Card className="text-red">{runQ.error.message}</Card>
      </Page>
    );
  }
  if (!run) {
    return (
      <Page title="Run" back={back}>
        <Spinner className="mx-auto text-accent" />
      </Page>
    );
  }
  const live = ACTIVE_RUN_STATUSES.includes(run.status);
  const status = RUN_STATUS[run.status];
  return (
    <Page title={run.policy} back={back}>
      <Card className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <p className="text-[14px] text-muted">
            {TRIGGERS[run.trigger]} · {dateTime(run.started_at)} ·{" "}
            {duration(run.started_at, run.ended_at)}
          </p>
          <Tag tone={status.tone}>
            {run.dry_run && run.status === "success" ? "Safety check passed" : status.label}
          </Tag>
        </div>
        {run.status === "running" && (
          <p className="text-[17px] font-bold text-accent">
            {run.dry_run ? "Safety check running…" : `${run.downloaded} new so far`}
          </p>
        )}
        {run.reason && <p className="text-[15px]">{run.reason}</p>}
        <div className="flex gap-2">
          {run.dry_run ? (
            <Stat label="Would download" value={run.would_download ?? 0} />
          ) : (
            <Stat label="Downloaded" value={run.downloaded} />
          )}
          {(run.filter_deleted > 0 || run.filter_kept > 0) && (
            <Stat label="Removed by filters" value={run.filter_deleted} />
          )}
          {!run.dry_run && !live && <Stat label="Files" value={run.file_count} />}
        </div>
        <div className="flex flex-wrap gap-2">
          {live && (
            <Button variant="danger" busy={stop.isPending} onClick={() => stop.mutate(run.id)}>
              Stop
            </Button>
          )}
          {run.log_path && (
            <Button variant="secondary" onClick={() => setShowLog((v) => !v)}>
              {showLog ? "Hide log" : "Show log"}
            </Button>
          )}
        </div>
        {stop.error && <p className="text-[14px] text-red">{stop.error.message}</p>}
        {!!run.unreadable && (
          <Link to={`/runs/${run.id}/photos`} className="text-[15px] font-semibold text-red">
            ⚠ {plural(run.unreadable, "file")} can't be read
          </Link>
        )}
        {!run.dry_run && run.downloaded > 0 && !live && (
          <Link to={`/runs/${run.id}/photos`} className="text-[15px] font-semibold text-accent">
            View photos
          </Link>
        )}
        {run.filter_kept > 0 && (
          <p className="text-[12px] text-muted">
            {plural(run.filter_kept, "file")} kept by filters
          </p>
        )}
      </Card>
      {run.gate_review && !policy.data && <Spinner className="mx-auto text-accent" />}
      {run.gate_review && policy.data && (
        <GateReview
          runId={run.id}
          review={run.gate_review}
          directory={policy.data.directory}
          threshold={policy.data.gate_threshold ?? settings.data?.gate_threshold ?? null}
        />
      )}
      {showLog && <LogView runId={run.id} live={live} />}
    </Page>
  );
}
