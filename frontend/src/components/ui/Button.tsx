"use client";

import { Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/cn";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "subtle";
export type ButtonSize = "sm" | "md" | "lg";

const VARIANTS: Record<ButtonVariant, string> = {
  // The single filled cyan action — the reference compositions use exactly one.
  primary:
    "bg-accent-500 text-navy-950 font-semibold shadow-glow-sm hover:bg-accent-400 " +
    "active:bg-accent-600 disabled:bg-navy-700 disabled:text-navy-400 disabled:shadow-none",
  secondary:
    "border border-navy-600/70 bg-navy-750/60 text-navy-100 hover:border-accent-500/50 " +
    "hover:bg-navy-700/70 hover:text-white disabled:opacity-40",
  ghost:
    "border border-transparent text-navy-300 hover:bg-navy-750/60 hover:text-navy-100 " +
    "disabled:opacity-40",
  danger:
    "border border-red-500/40 bg-red-500/10 text-red-200 hover:bg-red-500/20 " +
    "disabled:opacity-40",
  subtle:
    "border border-navy-700/60 bg-navy-800/50 text-navy-200 hover:bg-navy-750 " +
    "disabled:opacity-40",
};

const SIZES: Record<ButtonSize, string> = {
  sm: "h-8 gap-1.5 rounded-lg px-3 text-xs",
  md: "h-9 gap-2 rounded-lg px-3.5 text-sm",
  lg: "h-11 gap-2 rounded-xl px-5 text-sm",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Shows a spinner and disables the button. */
  isLoading?: boolean;
  icon?: ReactNode;
}

/** The single button primitive — every action in the app goes through this. */
export function Button({
  variant = "secondary",
  size = "md",
  isLoading = false,
  icon,
  className,
  children,
  disabled,
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      type={type}
      disabled={disabled || isLoading}
      className={cn(
        "inline-flex shrink-0 select-none items-center justify-center whitespace-nowrap",
        "transition-colors duration-150 ease-swift",
        "disabled:cursor-not-allowed",
        SIZES[size],
        VARIANTS[variant],
        className
      )}
    >
      {isLoading ? (
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
      ) : (
        icon
      )}
      {children}
    </button>
  );
}

export default Button;
