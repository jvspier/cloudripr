import * as RadixDialog from "@radix-ui/react-dialog";
import { AlertTriangle, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import type { LibraryItem } from "@/api/types";
import { dateTime } from "@/lib/format";
import { fileSize, isVideo, originalUrl, previewUrl } from "./media";

function Unreadable({ reason }: { reason: string }) {
  return (
    <div className="flex flex-col items-center gap-2 px-6 text-center text-white/80">
      <AlertTriangle aria-hidden className="size-10 text-red" />
      <p className="text-[15px]">{reason}</p>
    </div>
  );
}

/** The preview, or an explanation if it turns out the file can't be read. */
function Preview({ item }: { item: LibraryItem }) {
  const [failed, setFailed] = useState(false);
  if (failed) return <Unreadable reason="Can't be read: no preview could be made." />;
  return (
    <img
      src={previewUrl(item.id)}
      alt={item.name}
      onError={() => setFailed(true)}
      className="max-h-full max-w-full object-contain"
    />
  );
}

/** Larger look at one file, always dark. Read-only. */
export function Viewer({ item, onClose }: { item: LibraryItem | null; onClose: () => void }) {
  return (
    <RadixDialog.Root open={!!item} onOpenChange={(open) => !open && onClose()}>
      <RadixDialog.Portal>
        <RadixDialog.Content
          aria-describedby={undefined}
          className="fixed inset-0 z-50 flex flex-col bg-black text-white"
        >
          {item && (
            <>
              <div className="flex items-center gap-2 px-4 pb-2 pt-[calc(12px+env(safe-area-inset-top))]">
                <RadixDialog.Title className="flex-1 truncate text-[17px] font-semibold">
                  {item.name}
                </RadixDialog.Title>
                <RadixDialog.Close aria-label="Close" className="-mr-2 p-2">
                  <X className="size-6" />
                </RadixDialog.Close>
              </div>
              <div className="flex min-h-0 flex-1 items-center justify-center">
                {item.problem ? (
                  <Unreadable reason={item.problem} />
                ) : isVideo(item) ? (
                  <video
                    controls
                    playsInline
                    autoPlay
                    src={originalUrl(item.id)}
                    className="max-h-full max-w-full"
                  />
                ) : (
                  <Preview item={item} />
                )}
              </div>
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 px-4 pb-[calc(16px+env(safe-area-inset-bottom))] pt-3 text-[14px]">
                <dt className="text-white/60">Folder</dt>
                <dd>{item.folder}</dd>
                <dt className="text-white/60">Size</dt>
                <dd>{fileSize(item.size)}</dd>
                <dt className="text-white/60">Taken</dt>
                <dd>{dateTime(item.taken_at)}</dd>
                {item.run_id && (
                  <>
                    <dt className="text-white/60">Downloaded by</dt>
                    <dd>
                      <Link to={`/runs/${item.run_id}`} onClick={onClose} className="underline">
                        this run
                      </Link>
                    </dd>
                  </>
                )}
                {item.problem && (
                  <>
                    <dt className="text-white/60">Problem</dt>
                    <dd className="text-red">{item.problem}</dd>
                  </>
                )}
              </dl>
            </>
          )}
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}
