import type { ReactNode } from "react";

/** Screen wrapper: safe-area aware header and content column. */
export function Page({
  title,
  back,
  actions,
  wide = false,
  children,
}: {
  title: string;
  back?: ReactNode;
  actions?: ReactNode;
  /** Overview screens (Home, Photos) use more of a laptop screen; forms stay narrower. */
  wide?: boolean;
  children: ReactNode;
}) {
  return (
    <div
      className={`mx-auto flex w-full max-w-xl flex-col gap-4 px-4 pb-6 pt-[calc(16px+env(safe-area-inset-top))] md:px-8 md:pt-8 ${
        wide ? "md:max-w-4xl" : "md:max-w-2xl"
      }`}
    >
      <header className="flex min-h-10 items-center gap-2">
        {back}
        <h1 className="flex-1 text-[26px] font-bold tracking-tight">{title}</h1>
        {actions}
      </header>
      {children}
    </div>
  );
}
