import { AlertTriangle, ChevronLeft, Play } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { useLibraryItems } from "@/api/queries";
import type { LibraryItem } from "@/api/types";
import { Card, Page, Spinner } from "@/ui";
import { clock, isVideo, monthLabel, thumbUrl } from "./media";
import { Viewer } from "./Viewer";

export function Thumb({ item, onOpen }: { item: LibraryItem; onOpen?: () => void }) {
  const [failed, setFailed] = useState(false);
  const broken = !!item.problem || failed;
  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label={broken ? `${item.name}, can't be read` : item.name}
      className="relative aspect-square overflow-hidden bg-line"
    >
      {!broken && (
        <img
          src={thumbUrl(item.id)}
          alt=""
          loading="lazy"
          onError={() => setFailed(true)}
          className="size-full object-cover"
        />
      )}
      {broken && (
        <span className="absolute inset-0 flex items-center justify-center text-red">
          <AlertTriangle aria-hidden className="size-7" />
        </span>
      )}
      {isVideo(item) && (
        <span className="absolute bottom-1 right-1 flex items-center gap-0.5 rounded-full bg-black/60 px-1.5 text-[11px] font-semibold text-white">
          <Play aria-hidden className="size-3" />
          {item.duration != null ? clock(item.duration) : ""}
        </span>
      )}
    </button>
  );
}

function Grid({
  title,
  back,
  items,
}: {
  title: string;
  back: string;
  items: LibraryItem[] | undefined;
}) {
  const [open, setOpen] = useState<LibraryItem | null>(null);
  const backLink = (
    <Link to={back} aria-label="Back" className="-ml-2 p-2 text-muted">
      <ChevronLeft className="size-6" />
    </Link>
  );
  return (
    <Page title={title} back={backLink} wide>
      {!items ? (
        <Spinner className="mx-auto text-accent" />
      ) : items.length === 0 ? (
        <Card className="text-[15px] text-muted">No files here.</Card>
      ) : (
        <div className="-mx-4 grid grid-cols-3 gap-0.5 sm:mx-0 sm:grid-cols-5 sm:overflow-hidden sm:rounded-2xl md:grid-cols-6 lg:grid-cols-8">
          {items.map((item) => (
            <Thumb key={item.id} item={item} onOpen={() => setOpen(item)} />
          ))}
        </div>
      )}
      <Viewer item={open} onClose={() => setOpen(null)} />
    </Page>
  );
}

export function MonthPhotos() {
  const { ym = "" } = useParams();
  const items = useLibraryItems({ month: ym });
  return <Grid title={monthLabel(ym)} back="/photos" items={items.data} />;
}

export function RunPhotos() {
  const { id = "" } = useParams();
  const items = useLibraryItems({ run: id });
  return <Grid title="Downloaded in this run" back={`/runs/${id}`} items={items.data} />;
}
