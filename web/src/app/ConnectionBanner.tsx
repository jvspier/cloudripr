import { WifiOff } from "lucide-react";

export function ConnectionBanner() {
  return (
    <div
      role="status"
      className="fixed inset-x-0 top-0 z-40 flex items-center justify-center gap-2 bg-red px-4 pb-2 pt-[calc(8px+env(safe-area-inset-top))] text-[14px] font-semibold text-white"
    >
      <WifiOff aria-hidden className="size-4" />
      Connection lost — reconnecting…
    </div>
  );
}
