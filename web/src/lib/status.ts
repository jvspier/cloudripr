import type { Account, PolicySummary } from "@/api/types";
import { relTime } from "./format";

export interface HomeStatus {
  tone: "violet" | "red" | "green";
  title: string;
  detail: string;
  action?: { label: string; to: string };
}

/** The Home status card: the single most important thing, first match wins. */
export function homeStatus(
  account: Account,
  policies: PolicySummary[],
  justReauthed: boolean
): HomeStatus {
  if (account.state === "needs_reauth") {
    return {
      tone: "red",
      title: "iCloud needs you",
      detail: account.reason ?? "Apple wants you to sign in again.",
      action: { label: "Re-authenticate", to: "/account/reauth" },
    };
  }
  const gated = policies.find((p) => p.gate === "blocked" && p.gate_review);
  if (gated?.gate_review) {
    return {
      tone: "red",
      title: "Check before downloading",
      detail: `${gated.gate_review.count} files are waiting for your OK in ${gated.name}.`,
      action: { label: "Review", to: `/runs/${gated.gate_review.run_id}` },
    };
  }
  const broken = policies.find(
    (p) => p.last_run && ["failed", "skipped"].includes(p.last_run.status)
  );
  if (broken?.last_run) {
    return {
      tone: "red",
      title: "Last backup didn't finish",
      detail: broken.last_run.reason ?? "Open the run to see what happened.",
      action: { label: "View run", to: `/runs/${broken.last_run.id}` },
    };
  }
  if (!account.apple_id || !account.has_password) {
    return {
      tone: "red",
      title: "Set up your Apple ID",
      detail: "Add your Apple ID and password so backups can run.",
      action: { label: "Open settings", to: "/settings" },
    };
  }
  if (account.has_session === false) {
    return {
      tone: "red",
      title: "Sign in to iCloud",
      detail: "Backups can't run until you sign in once with a code from your iPhone.",
      action: { label: "Sign in", to: "/account/reauth" },
    };
  }
  if (justReauthed) {
    return {
      tone: "green",
      title: "All set",
      detail: "You're signed in again. Missed backups are catching up.",
    };
  }
  return {
    tone: "violet",
    title: "All good",
    detail:
      account.state === "unknown" || !account.last_verified_at
        ? "Waiting for the first check"
        : `Last checked ${relTime(account.last_verified_at)}`,
  };
}
