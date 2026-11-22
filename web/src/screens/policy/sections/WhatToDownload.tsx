import { Field, inputClass, Switch } from "@/ui";
import { NumberField, Section, type SectionProps } from "./common";
import { bool, str } from "./values";

export function WhatToDownload({ draft, setOpt, fieldError }: SectionProps) {
  const o = draft.icloudpd;
  const err = (k: string) => fieldError(`icloudpd.${k}`);
  return (
    <Section title="What to download">
      <Field label="Album" hint="Empty downloads everything" error={err("album")}>
        <input
          className={inputClass}
          value={str(o.album)}
          onChange={(e) => setOpt("album", e.target.value)}
        />
      </Field>
      <Switch
        label="Skip photos"
        checked={bool(o.skip_photos)}
        onChange={(v) => setOpt("skip_photos", v)}
      />
      <Switch
        label="Skip videos"
        checked={bool(o.skip_videos)}
        onChange={(v) => setOpt("skip_videos", v)}
      />
      <Switch
        label="Skip live photos"
        checked={bool(o.skip_live_photos)}
        onChange={(v) => setOpt("skip_live_photos", v)}
      />
      <NumberField
        label="Only the most recent"
        hint="Number of photos; empty for all"
        value={o.recent}
        onChange={(v) => setOpt("recent", v)}
        error={err("recent")}
      />
      <NumberField
        label="Stop after this many already-downloaded in a row"
        value={o.until_found}
        onChange={(v) => setOpt("until_found", v)}
        error={err("until_found")}
      />
      <Field
        label="Skip photos taken before"
        hint="A date like 2024-01-31 or an age like 30d"
        error={err("skip_created_before")}
      >
        <input
          className={inputClass}
          value={str(o.skip_created_before)}
          onChange={(e) => setOpt("skip_created_before", e.target.value)}
        />
      </Field>
      <Field
        label="Skip photos taken after"
        hint="A date like 2024-01-31 or an age like 30d"
        error={err("skip_created_after")}
      >
        <input
          className={inputClass}
          value={str(o.skip_created_after)}
          onChange={(e) => setOpt("skip_created_after", e.target.value)}
        />
      </Field>
      <Switch
        label="Write XMP sidecar files"
        checked={bool(o.xmp_sidecar)}
        onChange={(v) => setOpt("xmp_sidecar", v)}
      />
      <Switch
        label="Set EXIF date when missing"
        checked={bool(o.set_exif_datetime)}
        onChange={(v) => setOpt("set_exif_datetime", v)}
      />
    </Section>
  );
}
