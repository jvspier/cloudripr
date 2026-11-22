import type { Account, PolicySummary, Run } from "@/api/types";
import { account } from "./msw";

export const acct = (over: Partial<Account> = {}): Account => ({
  ...(account as Account),
  ...over,
});

export const run = (over: Partial<Run> = {}): Run => ({
  id: "r1",
  policy: "icloud",
  trigger: "schedule",
  status: "success",
  started_at: "2026-11-22T02:00:00+00:00",
  ended_at: "2026-11-22T02:20:00+00:00",
  reason: null,
  exit_code: 0,
  downloaded: 12,
  filter_kept: 0,
  filter_deleted: 0,
  dry_run: false,
  would_download: null,
  icloudpd_version: "1.32.3",
  log_path: "/data/runs/r1.log",
  ...over,
});

/** The real policy (tests/fixtures/policies/icloud.toml) as GET /api/policies returns it. */
export const pol = (over: Partial<PolicySummary> = {}): PolicySummary => ({
  name: "icloud",
  username: "me@example.com",
  directory: "/downloads",
  cron: "0 3 * * *",
  enabled: true,
  timezone: "Europe/Amsterdam",
  library_kind: "shared",
  icloudpd: {
    domain: "com",
    folder_structure: "{:%Y/%m}",
    size: ["original"],
    live_photo_size: "original",
    force_size: false,
    align_raw: "original",
    keep_unicode_in_filenames: false,
    set_exif_datetime: false,
    live_photo_mov_filename_policy: "suffix",
    file_match_policy: "name-size-dedup-with-suffix",
    xmp_sidecar: false,
    use_os_locale: false,
    skip_videos: false,
    skip_photos: false,
    skip_live_photos: false,
    auto_delete: false,
    cookie_directory: "/data/icloud-session",
  },
  filters: { file_suffixes: [], match_patterns: [], device_makes: [], device_models: [] },
  gate_threshold: null,
  next_run_at: "2026-11-23T02:00:00+00:00",
  last_run: run(),
  last_success: run(),
  active_run: null,
  gate: null,
  gate_review: null,
  naming_locked: true,
  ...over,
});
