import { Link } from "react-router";
import type { PolicySummary } from "@/api/types";
import { dateTime, plural } from "@/lib/format";
import { RUN_STATUS } from "@/lib/runLabels";
import { Card, Tag } from "@/ui";

/** The most recent finished run across all policies. */
export function LastNight({ policies }: { policies: PolicySummary[] }) {
  const latest = policies
    .map((p) => p.last_run)
    .filter((r) => r && r.ended_at)
    .sort((a, b) => b!.started_at.localeCompare(a!.started_at))[0];
  if (!latest) return null;
  const status = RUN_STATUS[latest.status];
  return (
    <Card className="flex items-center gap-3">
      <div className="flex-1">
        <p className="text-[13px] font-semibold text-muted">
          Latest backup · {dateTime(latest.started_at)}
        </p>
        <p className="text-[17px] font-bold">
          {latest.status === "success"
            ? latest.dry_run
              ? "Safety check passed"
              : plural(latest.downloaded, "new photo")
            : (latest.reason ?? status.label)}
        </p>
      </div>
      <Tag tone={status.tone}>{status.label}</Tag>
      {latest.status === "success" && !latest.dry_run && latest.downloaded > 0 && (
        <Link to={`/runs/${latest.id}/photos`} className="text-[15px] font-semibold text-accent">
          Photos
        </Link>
      )}
      <Link to={`/runs/${latest.id}`} className="text-[15px] font-semibold text-accent">
        View
      </Link>
    </Card>
  );
}
