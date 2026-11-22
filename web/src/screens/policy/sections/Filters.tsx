import type { Filters as FilterLists } from "@/api/types";
import { ListField, Section, type SectionProps } from "./common";

const LISTS: [keyof FilterLists, string, string][] = [
  ["file_suffixes", "File types to remove", "One per line, e.g. .png"],
  ["match_patterns", "File names to remove", "Regular expressions, one per line"],
  ["device_makes", "Camera makes to remove", "From the photo's EXIF data, e.g. Canon"],
  ["device_models", "Camera models to remove", "From the photo's EXIF data"],
];

export function Filters({ draft, set, fieldError }: SectionProps) {
  return (
    <Section title="Filters">
      <p className="text-[14px] text-muted">
        After each backup, matching files downloaded in that run are deleted locally. Applies only
        to files downloaded in that run.
      </p>
      {LISTS.map(([key, label, hint]) => (
        <ListField
          key={key}
          label={label}
          hint={hint}
          value={draft.filters[key]}
          error={fieldError(`filters.${key}`)}
          onChange={(v) => set({ filters: { ...draft.filters, [key]: v } })}
        />
      ))}
    </Section>
  );
}
