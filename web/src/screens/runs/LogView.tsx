import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiText } from "@/api/client";
import { Button, Card, Spinner } from "@/ui";

const TAIL = 2000;

export function LogView({ runId, live }: { runId: string; live: boolean }) {
  const [all, setAll] = useState(false);
  const log = useQuery({
    queryKey: ["runLog", runId],
    queryFn: () => apiText(`/runs/${encodeURIComponent(runId)}/log`),
    refetchInterval: live ? 3000 : false,
    retry: false,
  });
  if (log.error) return <Card className="text-[14px] text-red">{log.error.message}</Card>;
  if (log.data === undefined) return <Spinner className="mx-auto text-accent" />;
  const lines = log.data.split("\n");
  const hidden = all ? 0 : Math.max(0, lines.length - TAIL);
  return (
    <Card className="flex flex-col gap-2 p-3">
      {hidden > 0 && (
        <Button variant="ghost" onClick={() => setAll(true)}>
          Show all ({hidden} earlier lines hidden)
        </Button>
      )}
      <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap break-all font-mono text-[12px] leading-relaxed">
        {lines.slice(hidden).join("\n")}
      </pre>
    </Card>
  );
}
