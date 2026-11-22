import { Outlet } from "react-router";
import { useEvents } from "@/api/events";
import { useAccount, usePolicies } from "@/api/queries";
import { homeStatus } from "@/lib/status";
import { BottomBar } from "./BottomBar";
import { ConnectionBanner } from "./ConnectionBanner";

export function Shell() {
  const { connected } = useEvents();
  const account = useAccount();
  const policies = usePolicies();
  const attention =
    !!account.data &&
    !!policies.data &&
    homeStatus(account.data, policies.data, false).tone === "red";
  return (
    <div className="min-h-dvh pb-[calc(64px+env(safe-area-inset-bottom))] md:pb-0 md:pl-56">
      {!connected && <ConnectionBanner />}
      <Outlet />
      <BottomBar attention={attention} />
    </div>
  );
}
