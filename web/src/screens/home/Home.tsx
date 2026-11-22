import { useEffect, useState } from "react";
import { useLocation } from "react-router";
import { useAccount, usePolicies } from "@/api/queries";
import { homeStatus } from "@/lib/status";
import { Card, Page, Spinner } from "@/ui";
import { LastNight } from "./LastNight";
import { MigrationCard } from "./MigrationCard";
import { PolicyCard } from "./PolicyCard";
import { StatusCard } from "./StatusCard";

/** True for a minute after the re-auth flow sends the user here. */
function useJustReauthed(): boolean {
  const location = useLocation();
  const fromReauth = (location.state as { reauthed?: boolean } | null)?.reauthed === true;
  // The navigation (location.key) whose minute is up.
  const [expired, setExpired] = useState<string | null>(null);
  useEffect(() => {
    if (!fromReauth) return;
    const t = setTimeout(() => setExpired(location.key), 60_000);
    return () => clearTimeout(t);
  }, [fromReauth, location.key]);
  return fromReauth && expired !== location.key;
}

export function Home() {
  const account = useAccount();
  const policies = usePolicies();
  const justReauthed = useJustReauthed();

  if (account.error || policies.error) {
    return (
      <Page title="Backups" wide>
        <Card className="text-red">{(account.error ?? policies.error)!.message}</Card>
      </Page>
    );
  }
  if (!account.data || !policies.data) {
    return (
      <Page title="Backups" wide>
        <Spinner className="mx-auto text-accent" />
      </Page>
    );
  }
  const notes = account.data.migration_notes ?? [];
  return (
    <Page title="Backups" wide>
      <StatusCard status={homeStatus(account.data, policies.data, justReauthed)} />
      {notes.length > 0 && <MigrationCard notes={notes} />}
      <div className="grid gap-4 lg:grid-cols-2">
        <LastNight policies={policies.data} />
        {policies.data.map((p) => (
          <PolicyCard key={p.name} policy={p} />
        ))}
        {policies.data.length === 0 && (
          <Card className="text-[15px] text-muted">
            No backup policies yet. Add one under Settings → Policies.
          </Card>
        )}
      </div>
    </Page>
  );
}
