import { ChevronRight, Download, Plus, Upload } from "lucide-react";
import { useRef } from "react";
import { Link } from "react-router";
import { useImportPolicies, usePolicies } from "@/api/queries";
import { dateTime } from "@/lib/format";
import { Button, Card, Spinner, Tag } from "@/ui";

function readText(f: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(f);
  });
}

export function PolicyList() {
  const policies = usePolicies();
  const importer = useImportPolicies();
  const file = useRef<HTMLInputElement>(null);

  const onFile = async (f: File | undefined) => {
    if (f) importer.mutate(await readText(f));
    if (file.current) file.current.value = "";
  };

  return (
    <Card className="flex flex-col gap-1 p-2">
      {!policies.data && <Spinner className="mx-auto my-3 text-accent" />}
      {policies.data?.map((p) => (
        <Link
          key={p.name}
          to={`/settings/policies/${encodeURIComponent(p.name)}`}
          className="flex items-center gap-3 rounded-2xl p-3"
        >
          <div className="flex-1">
            <p className="font-semibold">{p.name}</p>
            <p className="text-[13px] text-muted">
              {p.enabled && p.next_run_at
                ? `Next ${dateTime(p.next_run_at, p.timezone)}`
                : "Paused"}
            </p>
          </div>
          {p.naming_locked && <Tag tone="muted">Naming locked</Tag>}
          <ChevronRight aria-hidden className="size-5 text-muted" />
        </Link>
      ))}
      <div className="flex flex-wrap gap-2 p-2">
        <Link
          to="/settings/policies/new"
          className="inline-flex min-h-11 items-center gap-1.5 rounded-full bg-soft-violet px-4 text-[15px] font-semibold text-accent"
        >
          <Plus aria-hidden className="size-4" /> Add policy
        </Link>
        <Button variant="ghost" busy={importer.isPending} onClick={() => file.current?.click()}>
          <Upload aria-hidden className="size-4" /> Import
        </Button>
        <a
          href="/api/policies/export"
          download
          className="inline-flex min-h-11 items-center gap-1.5 px-3 text-[15px] font-semibold text-muted"
        >
          <Download aria-hidden className="size-4" /> Export
        </a>
        <input
          ref={file}
          type="file"
          accept=".toml,application/toml,text/plain"
          hidden
          aria-label="Policy file"
          onChange={(e) => void onFile(e.target.files?.[0])}
        />
      </div>
      {importer.error && <p className="px-3 pb-2 text-[14px] text-red">{importer.error.message}</p>}
      {importer.data && (
        <div className="px-3 pb-2 text-[14px]">
          {importer.data.created.length > 0 && (
            <p>Imported: {importer.data.created.join(", ")}. Each starts with a safety check.</p>
          )}
          {importer.data.errors.map((e) => (
            <p key={`${e.name}-${e.error}`} className="text-red">
              {e.name ?? "Entry"}: {e.error}
            </p>
          ))}
        </div>
      )}
    </Card>
  );
}
