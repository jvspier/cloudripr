import { useState } from "react";
import { useUnlockPolicy } from "@/api/queries";
import { Button, Dialog, Field, inputClass } from "@/ui";

export function UnlockDialog({
  name,
  open,
  onOpenChange,
}: {
  name: string;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const [typed, setTyped] = useState("");
  const unlock = useUnlockPolicy();
  const close = (v: boolean) => {
    if (!v) setTyped("");
    onOpenChange(v);
  };
  return (
    <Dialog open={open} onOpenChange={close} title="Unlock file naming?">
      <div className="flex flex-col gap-4">
        <p className="text-[14px] text-muted">
          Changing these settings can make the next backup download everything again under new
          names. A safety check (dry run) will run first and ask before downloading many files.
        </p>
        <Field label={`Type ${name} to confirm`} error={unlock.error?.message}>
          <input
            className={inputClass}
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
          />
        </Field>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={() => close(false)}>
            Cancel
          </Button>
          <Button
            variant="danger"
            disabled={typed.trim() !== name}
            busy={unlock.isPending}
            onClick={() =>
              unlock.mutate({ name, confirm: typed }, { onSuccess: () => close(false) })
            }
          >
            Unlock naming
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
