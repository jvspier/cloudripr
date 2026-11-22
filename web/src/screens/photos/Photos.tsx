import { ChevronRight } from "lucide-react";
import { Link } from "react-router";
import { useLibraryMonths, useLibraryRuns, useLibrarySummary } from "@/api/queries";
import { dateTime, relTime } from "@/lib/format";
import { Card, Page, Section, Spinner } from "@/ui";
import { count, monthLabel } from "./media";
import { Thumb } from "./PhotoGrid";

/** A check that the syncs landed on disk, not a photo browser. */
export function Photos() {
  const summary = useLibrarySummary();
  const runs = useLibraryRuns();
  const months = useLibraryMonths();
  const s = summary.data;

  return (
    <Page title="Photos" wide>
      <Card className="flex flex-col gap-1">
        {!s ? (
          <Spinner className="mx-auto text-accent" />
        ) : (
          <>
            <p className="text-[17px] font-bold">
              On disk ~{count(s.on_disk)}
              {s.icloud && <span className="text-muted"> · iCloud {count(s.icloud.count)}</span>}
            </p>
            <p className="text-[14px] text-muted">
              {s.scanned_at ? `Last scan ${relTime(s.scanned_at)}` : "Not scanned yet"}
              {s.unreadable > 0 && (
                <span className="font-semibold text-red">
                  {" "}
                  · ⚠ {count(s.unreadable)} can't be read
                </span>
              )}
            </p>
          </>
        )}
      </Card>

      <Section title="Recent runs">
        {!runs.data ? (
          <Spinner className="mx-auto text-accent" />
        ) : runs.data.length === 0 ? (
          <p className="text-[15px] text-muted">No downloads yet.</p>
        ) : (
          runs.data.map((r) => (
            <div key={r.run.id} className="flex flex-col gap-2">
              <div className="flex items-center gap-2 text-[15px]">
                <span className="flex-1 font-semibold">
                  {dateTime(r.run.started_at)} · <span>{count(r.count)} new</span>
                </span>
                {!!r.unreadable && <span className="font-semibold text-red">⚠ {r.unreadable}</span>}
                <Link to={`/runs/${r.run.id}/photos`} className="font-semibold text-accent">
                  View
                </Link>
              </div>
              <div className="grid grid-cols-6 gap-0.5 overflow-hidden rounded-xl">
                {r.sample.map((item) => (
                  <Thumb key={item.id} item={item} />
                ))}
              </div>
            </div>
          ))
        )}
      </Section>

      <Section title="Library">
        {!months.data ? (
          <Spinner className="mx-auto text-accent" />
        ) : months.data.length === 0 ? (
          <p className="text-[15px] text-muted">Nothing indexed yet.</p>
        ) : (
          <ul className="-my-2 divide-y divide-line">
            {months.data.map((m) => (
              <li key={m.month}>
                <Link
                  to={`/photos/month/${m.month}`}
                  className="flex min-h-11 items-center gap-2 py-2 text-[15px]"
                >
                  <span className="flex-1 font-semibold">{monthLabel(m.month)}</span>
                  {m.unreadable > 0 && (
                    <span className="font-semibold text-red">⚠ {m.unreadable}</span>
                  )}
                  <span className="text-muted">{count(m.count)}</span>
                  <ChevronRight aria-hidden className="size-5 text-muted" />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </Page>
  );
}
