// Shapes returned by the /api backend (src/cloudripr/api/*).

export type AccountStateName = "unknown" | "ok" | "needs_reauth" | "reauthenticating";

export type AttemptState =
  | "starting"
  | "awaiting_code"
  | "sending_sms"
  | "awaiting_sms_code"
  | "verifying"
  | "succeeded"
  | "rejected"
  | "bad_password"
  | "expired"
  | "cancelled"
  | "failed";

export const FINAL_ATTEMPT_STATES: readonly AttemptState[] = [
  "succeeded",
  "rejected",
  "bad_password",
  "expired",
  "cancelled",
  "failed",
];

export interface Attempt {
  id: string;
  state: AttemptState;
  phones: { index: string; masked: string }[];
  error: string | null;
  sms_sent_to: string | null;
  started_at: string;
  ended_at: string | null;
}

export interface Account {
  apple_id: string | null;
  domain: "com" | "cn";
  has_password: boolean;
  state: AccountStateName;
  since: string | null;
  last_verified_at: string | null;
  reason: string | null;
  attempt: Attempt | null;
  busy_with: string | null;
  // GET /api/account only (absent in SSE "account" events):
  migration_notes?: string[];
  versions?: { app: string; icloudpd: string };
  email_last_error?: string | null;
  /** False until a sign-in has stored an Apple session. */
  has_session?: boolean;
}

export type RunStatus =
  | "queued"
  | "running"
  | "success"
  | "failed"
  | "stopped"
  | "needs_reauth"
  | "skipped"
  | "gate_blocked";

export const ACTIVE_RUN_STATUSES: readonly RunStatus[] = ["queued", "running"];

export interface Run {
  id: string;
  policy: string;
  trigger: "schedule" | "manual" | "catch-up" | "gate";
  status: RunStatus;
  started_at: string;
  ended_at: string | null;
  reason: string | null;
  exit_code: number | null;
  downloaded: number;
  filter_kept: number;
  filter_deleted: number;
  dry_run: boolean;
  would_download: number | null;
  icloudpd_version: string | null;
  log_path: string | null;
  /** New files of this run that can't be read; null until checked. */
  unreadable?: number | null;
}

// ---- Photos tab (sync check) ----

export interface LibraryItem {
  id: number;
  name: string;
  folder: string;
  kind: "photo" | "video" | "live" | "live_video";
  size: number;
  taken_at: string;
  duration: number | null;
  problem: string | null;
  run_id: string | null;
}

export interface LibrarySummary {
  on_disk: number;
  unreadable: number;
  scanned_at: string | null;
  icloud: { count: number; seen_at: string } | null;
}

export interface LibraryRun {
  run: Run;
  count: number;
  unreadable: number | null;
  sample: LibraryItem[];
}

export interface LibraryMonth {
  month: string;
  count: number;
  unreadable: number;
}

export interface GateReview {
  run_id: string;
  count: number;
  /** The check stopped early: at least `count` files would be downloaded. */
  partial?: boolean;
  sample: string[];
}

export interface RunDetail extends Run {
  file_count: number;
  gate_review: GateReview | null;
}

export interface Filters {
  file_suffixes: string[];
  match_patterns: string[];
  device_makes: string[];
  device_models: string[];
}

export interface Policy {
  name: string;
  username: string;
  directory: string;
  cron: string;
  enabled: boolean;
  timezone: string | null;
  icloudpd: Record<string, unknown>;
  library_kind: "personal" | "shared" | null;
  filters: Filters;
  gate_threshold: number | null;
  [extra: string]: unknown;
}

export interface PolicySummary extends Policy {
  next_run_at: string | null;
  last_run: Run | null;
  last_success: Run | null;
  active_run: Run | null;
  gate: "armed" | "blocked" | "approved" | null;
  gate_review: GateReview | null;
  naming_locked: boolean;
}

export interface EmailSettings {
  to: string | null;
  smtp_host: string;
  smtp_port: number;
  smtp_user: string | null;
  smtp_security: "starttls" | "ssl" | "none";
  extra_urls: string[];
  on_failure: boolean;
  on_success: boolean;
  app_url: string | null;
}

export interface Settings {
  email: EmailSettings;
  retention_runs: number;
  idle_timeout_minutes: number;
  session_check_time: string;
  gate_threshold: number;
  smtp_password_set: boolean;
  email_last_error: string | null;
}

export interface AttemptRecord {
  id: string;
  started_at: string;
  ended_at: string | null;
  outcome: string | null;
  log_path: string | null;
}

export interface AuthStatus {
  authenticated: boolean;
  setup_required: boolean;
}
