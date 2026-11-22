import type { FormEvent, ReactNode } from "react";
import { Card } from "@/ui";

export function AuthCard({
  title,
  intro,
  onSubmit,
  children,
}: {
  title: string;
  intro: string;
  onSubmit: () => void;
  children: ReactNode;
}) {
  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit();
  };
  return (
    <div className="flex min-h-dvh items-center justify-center px-4 pt-[env(safe-area-inset-top)]">
      <Card className="w-full max-w-sm">
        <form onSubmit={submit} className="flex flex-col gap-4">
          <div>
            <h1 className="text-[22px] font-bold">{title}</h1>
            <p className="text-[14px] text-muted">{intro}</p>
          </div>
          {children}
        </form>
      </Card>
    </div>
  );
}
