import { useId, type ReactElement, type ReactNode } from "react";
import { cloneElement } from "react";

export const inputClass =
  "w-full rounded-xl border border-line bg-card px-3 py-2.5 text-[16px] text-text outline-none focus:border-violet disabled:opacity-60";

/** Label + control + hint/error. The single child control gets the id and aria wiring. */
export function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: ReactNode;
  error?: string | null;
  children: ReactElement<{ id?: string; "aria-invalid"?: boolean; "aria-describedby"?: string }>;
}) {
  const id = useId();
  const noteId = `${id}-note`;
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-[13px] font-semibold text-muted">
        {label}
      </label>
      {cloneElement(children, {
        id,
        "aria-invalid": error ? true : undefined,
        "aria-describedby": error || hint ? noteId : undefined,
      })}
      {error ? (
        <p id={noteId} className="text-[13px] text-red">
          {error}
        </p>
      ) : hint ? (
        <p id={noteId} className="text-[13px] text-muted">
          {hint}
        </p>
      ) : null}
    </div>
  );
}
