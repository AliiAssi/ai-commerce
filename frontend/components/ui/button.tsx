import Link from "next/link";
import type { ComponentPropsWithoutRef, ReactNode } from "react";

import { cn } from "@/lib/cn";

const BASE =
  "inline-flex items-center justify-center gap-2 rounded-el uppercase tracking-wide transition-colors disabled:opacity-40 disabled:cursor-not-allowed";

const VARIANTS = {
  primary:
    "border border-brand bg-brand text-brand-contrast hover:bg-transparent hover:text-brand",
  secondary: "border border-border bg-surface text-ink hover:border-brand hover:text-brand",
  ghost: "text-brand hover:bg-brand-subtle",
  danger:
    "border border-danger bg-danger text-brand-contrast hover:bg-transparent hover:text-danger",
  "danger-outline": "border border-danger text-danger hover:bg-danger-subtle",
} as const;

const SIZES = {
  sm: "text-xs px-3 py-1.5",
  md: "text-xs px-4 py-2.5",
  lg: "text-sm px-7 py-3.5",
} as const;

export type ButtonVariant = keyof typeof VARIANTS;
export type ButtonSize = keyof typeof SIZES;

interface CommonProps {
  children: ReactNode;
  variant?: ButtonVariant;
  size?: ButtonSize;
  block?: boolean;
  className?: string;
}

type ButtonProps = CommonProps &
  Omit<ComponentPropsWithoutRef<"button">, "className" | "children">;

type LinkButtonProps = CommonProps & { href: string } & Omit<
    ComponentPropsWithoutRef<typeof Link>,
    "className" | "children" | "href"
  >;

function classes({ variant = "primary", size = "md", block, className }: CommonProps) {
  return cn(BASE, VARIANTS[variant], SIZES[size], block && "w-full", className);
}

export function Button({ children, variant, size, block, className, ...rest }: ButtonProps) {
  return (
    <button
      type="button"
      className={classes({ children, variant, size, block, className })}
      {...rest}
    >
      {children}
    </button>
  );
}

export function LinkButton({
  children,
  variant,
  size,
  block,
  className,
  href,
  ...rest
}: LinkButtonProps) {
  return (
    <Link
      href={href}
      className={classes({ children, variant, size, block, className })}
      {...rest}
    >
      {children}
    </Link>
  );
}
