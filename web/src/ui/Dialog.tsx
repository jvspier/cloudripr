import * as RadixDialog from "@radix-ui/react-dialog";
import type { ReactNode } from "react";

export function Dialog({
  open,
  onOpenChange,
  title,
  children,
  sheet = false,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  title: string;
  children: ReactNode;
  /** Bottom sheet instead of a centred dialog. */
  sheet?: boolean;
}) {
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="fixed inset-0 z-40 bg-black/40" />
        <RadixDialog.Content
          aria-describedby={undefined}
          className={
            sheet
              ? "fixed inset-x-0 bottom-0 z-50 max-h-[85vh] overflow-auto rounded-t-[24px] bg-card p-5 pb-[calc(20px+env(safe-area-inset-bottom))] text-text"
              : "fixed left-1/2 top-1/2 z-50 w-[min(92vw,420px)] -translate-x-1/2 -translate-y-1/2 rounded-card bg-card p-5 text-text"
          }
        >
          <RadixDialog.Title className="mb-3 text-[17px] font-bold">{title}</RadixDialog.Title>
          {children}
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}

export function Sheet(props: Omit<Parameters<typeof Dialog>[0], "sheet">) {
  return <Dialog {...props} sheet />;
}
