import type { ReactNode } from "react";
import { Card } from "./Card";

/** A titled group of settings; `anchor` makes it linkable as /settings#anchor. */
export function Section({
  title,
  anchor,
  children,
}: {
  title: string;
  anchor?: string;
  children: ReactNode;
}) {
  const id = `section-${title.toLowerCase().replace(/\W+/g, "-")}`;
  return (
    <section id={anchor} aria-labelledby={id} className="scroll-mt-4">
      <h2 id={id} className="mb-2 px-1 text-[13px] font-bold uppercase tracking-wide text-muted">
        {title}
      </h2>
      <Card className="flex flex-col gap-4">{children}</Card>
    </section>
  );
}
