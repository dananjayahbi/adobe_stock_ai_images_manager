import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-oxblood-500 text-parchment-50 border-oxblood-600 hover:bg-oxblood-600 shadow-card",
  secondary:
    "bg-parchment-50 text-ink-800 border-parchment-500 hover:bg-parchment-200 hover:border-parchment-600",
  ghost:
    "bg-transparent text-ink-600 border-transparent hover:bg-parchment-200 hover:text-ink-800",
  danger:
    "bg-rust-500 text-parchment-50 border-rust-600 hover:bg-rust-600",
};

const SIZES: Record<Size, string> = {
  sm: "px-3 py-1.5 text-[11px]",
  md: "px-4 py-2 text-xs",
  lg: "px-6 py-3 text-sm",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  children: ReactNode;
}

/**
 * Letterpress-style button: hairline border, small-caps label, warm states.
 * The label stays in the DOM while loading (with a spinner) so widths — and
 * therefore nearby layout — never jump.
 */
export default function Button({
  variant = "primary",
  size = "md",
  loading = false,
  disabled,
  children,
  className = "",
  ...rest
}: ButtonProps) {
  return (
    <button
      disabled={disabled || loading}
      className={`inline-flex items-center justify-center gap-2 rounded-sm border font-stamp uppercase tracking-[0.14em] transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-brass-400 disabled:cursor-not-allowed disabled:opacity-50 ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
      {...rest}
    >
      {loading && (
        <span className="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
      )}
      {children}
    </button>
  );
}
