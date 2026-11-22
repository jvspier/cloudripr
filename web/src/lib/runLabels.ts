import type { RunStatus } from "@/api/types";

export const RUN_STATUS: Record<
  RunStatus,
  { label: string; tone: "ok" | "red" | "violet" | "muted" }
> = {
  queued: { label: "Queued", tone: "violet" },
  running: { label: "Running", tone: "violet" },
  success: { label: "Done", tone: "ok" },
  failed: { label: "Failed", tone: "red" },
  stopped: { label: "Stopped", tone: "muted" },
  needs_reauth: { label: "Needs sign-in", tone: "red" },
  skipped: { label: "Skipped", tone: "red" },
  gate_blocked: { label: "Waiting for your OK", tone: "red" },
};
