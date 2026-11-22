import type { HTMLAttributes } from "react";

type Tone = "plain" | "violet" | "red" | "green";

const TONES: Record<Tone, string> = {
  plain: "bg-card text-text",
  violet: "bg-grad-violet text-white",
  red: "bg-grad-red text-white",
  green: "bg-grad-green text-white",
};

export function Card({
  tone = "plain",
  className = "",
  ...rest
}: HTMLAttributes<HTMLDivElement> & { tone?: Tone }) {
  return <div className={`rounded-card p-4 shadow-sm ${TONES[tone]} ${className}`} {...rest} />;
}
