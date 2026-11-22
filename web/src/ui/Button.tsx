import type { ButtonHTMLAttributes } from "react";
import { Spinner } from "./Spinner";

type Variant = "primary" | "secondary" | "danger" | "ghost" | "light";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-violet text-white",
  secondary: "bg-soft-violet text-accent",
  danger: "bg-red text-white",
  ghost: "bg-transparent text-muted",
  light: "bg-white text-text",
};

export function Button({
  variant = "primary",
  busy = false,
  disabled,
  className = "",
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; busy?: boolean }) {
  return (
    <button
      type="button"
      disabled={disabled || busy}
      className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-full px-5 text-[15px] font-semibold disabled:opacity-50 ${VARIANTS[variant]} ${className}`}
      {...rest}
    >
      {busy && <Spinner />}
      {children}
    </button>
  );
}
