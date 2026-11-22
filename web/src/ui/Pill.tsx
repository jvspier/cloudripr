import type { ReactNode } from "react";

export function Pill({ active = false, children }: { active?: boolean; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-3 py-1 text-[13px] font-semibold ${
        active ? "bg-pill text-[#3b2f00]" : "bg-white/20 text-current"
      }`}
    >
      {children}
    </span>
  );
}

type TagTone = "ok" | "red" | "violet" | "muted";

const TAGS: Record<TagTone, string> = {
  ok: "bg-soft-green text-green-dark dark:text-green",
  red: "bg-soft-red text-red-dark dark:text-red",
  violet: "bg-soft-violet text-accent",
  muted: "bg-line text-muted",
};

export function Tag({ tone, children }: { tone: TagTone; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[12px] font-semibold ${TAGS[tone]}`}
    >
      {children}
    </span>
  );
}
