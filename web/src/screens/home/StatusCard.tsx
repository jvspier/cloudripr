import { AlertTriangle, CheckCircle2, ShieldCheck } from "lucide-react";
import { Link } from "react-router";
import type { HomeStatus } from "@/lib/status";
import { Card } from "@/ui";

const ICONS = { violet: ShieldCheck, red: AlertTriangle, green: CheckCircle2 };

export function StatusCard({ status }: { status: HomeStatus }) {
  const Icon = ICONS[status.tone];
  return (
    <Card tone={status.tone} className="flex flex-col gap-3 p-5">
      <div className="flex items-start gap-3">
        <Icon aria-hidden className="mt-0.5 size-7 shrink-0" />
        <div>
          <h2 className="text-[22px] font-bold leading-tight">{status.title}</h2>
          <p className="text-[15px] opacity-90">{status.detail}</p>
        </div>
      </div>
      {status.action && (
        <Link
          to={status.action.to}
          className="inline-flex min-h-11 items-center justify-center self-start rounded-full bg-white px-5 text-[15px] font-semibold text-[#1a1830]"
        >
          {status.action.label}
        </Link>
      )}
    </Card>
  );
}
