import { ChevronLeft } from "lucide-react";
import { useCallback, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router";
import { ApiError } from "@/api/client";
import { useDeletePolicy, usePolicy, useRunPolicy, useSavePolicy } from "@/api/queries";
import type { Policy } from "@/api/types";
import { namingChanged, toPolicyBody } from "@/lib/policyBody";
import { Button, Card, Dialog, Page, Spinner } from "@/ui";
import { Basics } from "./sections/Basics";
import { Filters } from "./sections/Filters";
import { FileNaming } from "./sections/FileNaming";
import { ICloudCleanup } from "./sections/ICloudCleanup";
import { Safety } from "./sections/Safety";
import { Schedule } from "./sections/Schedule";
import { WhatToDownload } from "./sections/WhatToDownload";
import { UnlockDialog } from "./UnlockDialog";

function newPolicy(): Policy {
  return {
    name: "",
    username: "",
    directory: "/downloads/",
    cron: "0 3 * * *",
    enabled: true,
    timezone: null,
    library_kind: "personal",
    icloudpd: {
      folder_structure: "{:%Y/%m}",
      size: ["original"],
      live_photo_size: "original",
      live_photo_mov_filename_policy: "suffix",
      file_match_policy: "name-size-dedup-with-suffix",
      align_raw: "original",
    },
    filters: { file_suffixes: [], match_patterns: [], device_makes: [], device_models: [] },
    gate_threshold: null,
  };
}

const clone = <T,>(v: T): T => structuredClone(v);

export function PolicyEditor() {
  const { name } = useParams();
  const isNew = !name;
  const navigate = useNavigate();
  const location = useLocation();
  const policyQ = usePolicy(name);
  const original = policyQ.data ?? null;
  const save = useSavePolicy();
  const runNow = useRunPolicy();
  const del = useDeletePolicy();
  const [draft, setDraft] = useState<Policy | null>(isNew ? newPolicy() : null);
  const [dirTouched, setDirTouched] = useState(false);
  const [saved, setSaved] = useState(
    (location.state as { saved?: boolean } | null)?.saved === true
  );
  const [unlocking, setUnlocking] = useState(false);
  const [deleting, setDeleting] = useState(false);

  if (original && !draft) setDraft(clone(original));

  const edit = useCallback((fn: (d: Policy) => Policy) => {
    setSaved(false);
    setDraft((d) => (d ? fn(d) : d));
  }, []);

  const back = (
    <Link to="/settings#policies" aria-label="Back" className="-ml-2 p-2 text-muted">
      <ChevronLeft className="size-6" />
    </Link>
  );
  const title = isNew ? "New policy" : (name ?? "");

  if (policyQ.error) {
    return (
      <Page title={title} back={back}>
        <Card className="text-red">{policyQ.error.message}</Card>
      </Page>
    );
  }
  if (!draft) {
    return (
      <Page title={title} back={back}>
        <Spinner className="mx-auto text-accent" />
      </Page>
    );
  }

  const apiError = save.error instanceof ApiError ? save.error : null;
  const fieldError = (field: string) => (apiError?.field === field ? apiError.message : undefined);
  const props = {
    draft,
    fieldError,
    set: (patch: Partial<Policy>) => edit((d) => ({ ...d, ...patch })),
    setOpt: (key: string, value: unknown) =>
      edit((d) => {
        const icloudpd = { ...d.icloudpd };
        if (value === undefined || value === null || value === "") delete icloudpd[key];
        else icloudpd[key] = value;
        return { ...d, icloudpd };
      }),
  };
  const locked = original?.naming_locked === true;

  const onSave = () =>
    save.mutate(toPolicyBody(original, draft), {
      onSuccess: (p) => {
        setSaved(true);
        if (isNew)
          navigate(`/settings/policies/${encodeURIComponent(p.name)}`, {
            replace: true,
            state: { saved: true },
          });
        else setDraft(clone(p));
      },
    });

  return (
    <Page title={title} back={back}>
      <Basics
        {...props}
        isNew={isNew}
        onName={(n) =>
          edit((d) => ({ ...d, name: n, directory: dirTouched ? d.directory : `/downloads/${n}` }))
        }
      />
      <Schedule {...props} />
      <WhatToDownload {...props} />
      <FileNaming
        {...props}
        set={(patch) => {
          if ("directory" in patch) setDirTouched(true);
          props.set(patch);
        }}
        locked={locked}
        changed={!!original && namingChanged(original, draft)}
        onUnlock={() => setUnlocking(true)}
      />
      <Filters {...props} />
      <ICloudCleanup {...props} />
      <Safety {...props} />

      <div className="sticky bottom-[calc(72px+env(safe-area-inset-bottom))] flex flex-col gap-2 rounded-card bg-card p-3 shadow-lg">
        {save.error && (
          <p role="alert" className="text-[14px] text-red">
            {`Couldn't save: ${save.error.message}`}
          </p>
        )}
        <div className="flex items-center gap-2">
          <Button busy={save.isPending} disabled={isNew && !draft.name} onClick={onSave}>
            Save
          </Button>
          {saved && (
            <span className="text-[14px] font-semibold text-green-dark dark:text-green">Saved</span>
          )}
          <span className="flex-1" />
          {!isNew && (
            <Button
              variant="secondary"
              busy={runNow.isPending}
              onClick={() =>
                runNow.mutate(draft.name, { onSuccess: (r) => navigate(`/runs/${r.id}`) })
              }
            >
              Run now
            </Button>
          )}
        </div>
      </div>

      {!isNew && (
        <Button variant="ghost" className="text-red" onClick={() => setDeleting(true)}>
          Delete policy
        </Button>
      )}

      {!isNew && <UnlockDialog name={draft.name} open={unlocking} onOpenChange={setUnlocking} />}
      <Dialog open={deleting} onOpenChange={setDeleting} title={`Delete ${draft.name}?`}>
        <p className="mb-4 text-[14px] text-muted">
          The policy and its schedule are removed. Downloaded photos stay where they are.
        </p>
        {del.error && <p className="mb-2 text-[14px] text-red">{del.error.message}</p>}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setDeleting(false)}>
            Cancel
          </Button>
          <Button
            variant="danger"
            busy={del.isPending}
            onClick={() =>
              del.mutate(draft.name, { onSuccess: () => navigate("/settings#policies") })
            }
          >
            Delete
          </Button>
        </div>
      </Dialog>
    </Page>
  );
}
