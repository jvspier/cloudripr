import { Switch } from "@/ui";
import { NumberField, Section, type SectionProps } from "./common";
import { bool } from "./values";

const warn = (text: string) => <span className="text-red">{text}</span>;

export function ICloudCleanup({ draft, setOpt, fieldError }: SectionProps) {
  const o = draft.icloudpd;
  return (
    <Section title="iCloud cleanup">
      <Switch
        label="Mirror deletions"
        hint={warn("Deletes downloaded files that you deleted in iCloud")}
        checked={bool(o.auto_delete)}
        onChange={(v) => setOpt("auto_delete", v)}
      />
      <Switch
        label="Delete from iCloud after download"
        hint={warn("Deletes photos from iCloud")}
        checked={bool(o.delete_after_download)}
        onChange={(v) => setOpt("delete_after_download", v)}
      />
      <NumberField
        label="Keep the most recent days in iCloud"
        hint={warn("Deletes older photos from iCloud; empty keeps everything")}
        value={o.keep_icloud_recent_days}
        onChange={(v) => setOpt("keep_icloud_recent_days", v)}
        error={fieldError("icloudpd.keep_icloud_recent_days")}
      />
    </Section>
  );
}
