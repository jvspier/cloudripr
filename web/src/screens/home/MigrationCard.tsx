import { Sparkles } from "lucide-react";
import { useDismissNotes } from "@/api/queries";
import { Button, Card } from "@/ui";

export function MigrationCard({ notes }: { notes: string[] }) {
  const dismiss = useDismissNotes();
  return (
    <Card className="flex flex-col gap-3">
      <h2 className="flex items-center gap-2 text-[17px] font-bold">
        <Sparkles aria-hidden className="size-5 text-accent" /> What changed
      </h2>
      <ul className="flex list-disc flex-col gap-1 pl-5 text-[14px]">
        {notes.map((n) => (
          <li key={n}>{n}</li>
        ))}
      </ul>
      <Button
        variant="secondary"
        className="self-start"
        busy={dismiss.isPending}
        onClick={() => dismiss.mutate()}
      >
        Got it
      </Button>
    </Card>
  );
}
