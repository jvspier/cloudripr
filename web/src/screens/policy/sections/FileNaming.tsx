import { Lock, LockOpen } from "lucide-react";
import { Button, Field, inputClass, Switch } from "@/ui";
import { SelectField, Section, type SectionProps } from "./common";
import { bool, str } from "./values";

const SIZES = ["original", "medium", "thumb", "adjusted", "alternative"] as const;

export function FileNaming({
  draft,
  set,
  setOpt,
  fieldError,
  locked,
  changed,
  onUnlock,
}: SectionProps & { locked: boolean; changed: boolean; onUnlock: () => void }) {
  const o = draft.icloudpd;
  const err = (k: string) => fieldError(`icloudpd.${k}`);
  const sizes = Array.isArray(o.size) ? (o.size as string[]) : [];
  return (
    <Section title="File naming">
      {locked ? (
        <div className="flex items-center gap-3 rounded-2xl bg-soft-violet p-3">
          <Lock aria-hidden className="size-5 shrink-0 text-accent" />
          <p className="flex-1 text-[14px]">Locked to protect your existing downloads</p>
          <Button variant="secondary" onClick={onUnlock}>
            Unlock
          </Button>
        </div>
      ) : (
        changed && (
          <div className="flex items-center gap-3 rounded-2xl bg-soft-violet p-3 text-[14px]">
            <LockOpen aria-hidden className="size-5 shrink-0 text-accent" />
            Saving will run a safety check (dry run) before the next download.
          </div>
        )
      )}
      <Field
        label="Download folder"
        hint="Inside the container, e.g. /downloads"
        error={fieldError("directory")}
      >
        <input
          className={inputClass}
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          disabled={locked}
          value={draft.directory}
          onChange={(e) => set({ directory: e.target.value })}
        />
      </Field>
      <SelectField
        label="Library"
        value={draft.library_kind}
        options={[
          ["personal", "Personal library"],
          ["shared", "Shared library"],
        ]}
        onChange={(v) => set({ library_kind: v })}
        disabled={locked}
        error={fieldError("library_kind")}
      />
      <Field
        label="Folder structure"
        hint="{:%Y/%m} puts photos in year/month folders"
        error={err("folder_structure")}
      >
        <input
          className={`${inputClass} font-mono`}
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          disabled={locked}
          value={str(o.folder_structure)}
          onChange={(e) => setOpt("folder_structure", e.target.value)}
        />
      </Field>
      <fieldset disabled={locked} className="flex flex-col gap-1.5">
        <legend className="mb-1.5 text-[13px] font-semibold text-muted">Sizes</legend>
        <div className="flex flex-wrap gap-3">
          {SIZES.map((s) => (
            <label key={s} className="flex items-center gap-1.5 text-[15px]">
              <input
                type="checkbox"
                className="size-5 accent-[var(--violet-2)]"
                checked={sizes.includes(s)}
                onChange={(e) =>
                  setOpt("size", e.target.checked ? [...sizes, s] : sizes.filter((x) => x !== s))
                }
              />
              {s}
            </label>
          ))}
        </div>
        {err("size") && <p className="text-[13px] text-red">{err("size")}</p>}
      </fieldset>
      <SelectField
        label="Live photo video size"
        value={str(o.live_photo_size) || null}
        options={[
          ["original", "original"],
          ["medium", "medium"],
          ["thumb", "thumb"],
        ]}
        onChange={(v) => setOpt("live_photo_size", v)}
        disabled={locked}
        error={err("live_photo_size")}
      />
      <SelectField
        label="Live photo video names"
        value={str(o.live_photo_mov_filename_policy) || null}
        options={[
          ["suffix", "IMG_1234_HEVC.MOV (suffix)"],
          ["original", "IMG_1234.MOV (original)"],
        ]}
        onChange={(v) => setOpt("live_photo_mov_filename_policy", v)}
        disabled={locked}
        error={err("live_photo_mov_filename_policy")}
      />
      <SelectField
        label="RAW alignment"
        value={str(o.align_raw) || null}
        options={[
          ["original", "original"],
          ["alternative", "alternative"],
          ["as-is", "as-is"],
        ]}
        onChange={(v) => setOpt("align_raw", v)}
        disabled={locked}
        error={err("align_raw")}
      />
      <SelectField
        label="Duplicate names"
        value={str(o.file_match_policy) || null}
        options={[
          ["name-size-dedup-with-suffix", "Add a suffix when name and size differ"],
          ["name-id7", "Add a short ID to every name"],
        ]}
        onChange={(v) => setOpt("file_match_policy", v)}
        disabled={locked}
        error={err("file_match_policy")}
      />
      <Switch
        label="Only download the chosen size"
        hint="force_size"
        checked={bool(o.force_size)}
        onChange={(v) => setOpt("force_size", v)}
        disabled={locked}
      />
      <Switch
        label="Keep non-ASCII characters in names"
        checked={bool(o.keep_unicode_in_filenames)}
        onChange={(v) => setOpt("keep_unicode_in_filenames", v)}
        disabled={locked}
      />
    </Section>
  );
}
