import type { Policy, PolicySummary } from "@/api/types";

/** Settings that decide file paths and names; locked once a policy has run. */
export const NAMING_FIELDS = [
  "directory",
  "library_kind",
  "icloudpd.folder_structure",
  "icloudpd.size",
  "icloudpd.live_photo_size",
  "icloudpd.live_photo_mov_filename_policy",
  "icloudpd.align_raw",
  "icloudpd.force_size",
  "icloudpd.file_match_policy",
  "icloudpd.keep_unicode_in_filenames",
] as const;

const SUMMARY_KEYS = [
  "next_run_at",
  "last_run",
  "last_success",
  "active_run",
  "gate",
  "gate_review",
  "naming_locked",
] as const;

export function getField(p: Policy, field: (typeof NAMING_FIELDS)[number]): unknown {
  return field.startsWith("icloudpd.") ? p.icloudpd[field.slice(9)] : p[field];
}

/** True when any naming value in `draft` differs from `original`. */
export function namingChanged(original: Policy, draft: Policy): boolean {
  return NAMING_FIELDS.some(
    (f) =>
      JSON.stringify(getField(original, f) ?? null) !== JSON.stringify(getField(draft, f) ?? null)
  );
}

/**
 * The PUT body: the whole draft (keys without an editor field ride along), minus
 * server-only summary keys; locked naming values always come from the original.
 */
export function toPolicyBody(original: PolicySummary | null, draft: Policy): Policy {
  const body: Policy = { ...draft, icloudpd: { ...draft.icloudpd } };
  for (const key of SUMMARY_KEYS) delete body[key];
  if (original?.naming_locked) {
    for (const field of NAMING_FIELDS) {
      if (field.startsWith("icloudpd.")) {
        const key = field.slice(9);
        if (key in original.icloudpd) body.icloudpd[key] = original.icloudpd[key];
        else delete body.icloudpd[key];
      } else {
        (body as Record<string, unknown>)[field] = original[field];
      }
    }
  }
  return body;
}
