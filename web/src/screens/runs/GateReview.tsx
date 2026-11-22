import { ShieldAlert } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router";
import { useApproveRun } from "@/api/queries";
import type { GateReview as Review } from "@/api/types";
import { folderBreakdown } from "@/lib/gate";
import { Button, Card, Dialog } from "@/ui";

const SHOWN = 50;

export function GateReview({
  runId,
  review,
  directory,
  threshold,
}: {
  runId: string;
  review: Review;
  directory: string;
  threshold: number | null;
}) {
  const navigate = useNavigate();
  const approve = useApproveRun();
  const [confirming, setConfirming] = useState(false);
  const rows = folderBreakdown(review.sample, directory);

  const go = () =>
    approve.mutate(runId, {
      onSuccess: (next) => {
        setConfirming(false);
        navigate(`/runs/${next.id}`);
      },
    });

  return (
    <Card className="flex flex-col gap-4 border border-red/40">
      <div className="flex items-start gap-3">
        <ShieldAlert aria-hidden className="size-7 shrink-0 text-red" />
        <div>
          <h2 className="text-[19px] font-bold">
            {review.partial ? `At least ${review.count}` : review.count} files would be downloaded
          </h2>
          <p className="text-[14px] text-muted">
            The safety check stopped because this is more than{" "}
            {threshold !== null ? `the limit of ${threshold}` : "the limit"}
            {review.partial ? ", and it stopped counting early" : ""}. If your photos were already
            downloaded, this can mean the file naming changed — downloading would create copies.
          </p>
        </div>
      </div>
      <div>
        <h3 className="mb-1 text-[13px] font-semibold text-muted">
          Folders · From a sample of {review.sample.length}
        </h3>
        <table className="w-full text-[14px]">
          <tbody>
            {rows.map((r) => (
              <tr key={r.folder} className="border-t border-line">
                <td className="py-1.5">{r.folder}</td>
                <td className="py-1.5 text-right font-semibold">{r.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details>
        <summary className="cursor-pointer text-[14px] font-semibold text-accent">
          Example files
        </summary>
        <ul className="mt-2 flex flex-col gap-1 break-all font-mono text-[12px]">
          {review.sample.slice(0, SHOWN).map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      </details>
      <div className="flex flex-wrap gap-2">
        <Button variant="danger" onClick={() => setConfirming(true)}>
          Download them
        </Button>
        <Button variant="secondary" onClick={() => navigate("/")}>
          Keep blocked
        </Button>
      </div>
      <Dialog
        open={confirming}
        onOpenChange={setConfirming}
        title={
          review.partial
            ? `Download all new files into ${directory}?`
            : `Download ${review.count} files into ${directory}?`
        }
      >
        <p className="mb-4 text-[14px] text-muted">
          The backup starts right away. Only do this if these files are really new.
        </p>
        {approve.error && <p className="mb-2 text-[14px] text-red">{approve.error.message}</p>}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setConfirming(false)}>
            Cancel
          </Button>
          <Button variant="danger" busy={approve.isPending} onClick={go}>
            Yes, download
          </Button>
        </div>
      </Dialog>
    </Card>
  );
}
