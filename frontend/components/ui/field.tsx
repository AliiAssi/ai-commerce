import type { ComponentPropsWithoutRef, ReactNode } from "react";

import { cn } from "@/lib/cn";

const INPUT =
  "w-full rounded-el border border-border bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-brand focus:outline-none";
const LABEL = "mb-1 block text-[0.6875rem] uppercase tracking-label text-ink-faint";

function Wrapper({ label, children }: { label: ReactNode; children: ReactNode }) {
  return (
    <label className="block">
      <span className={LABEL}>{label}</span>
      {children}
    </label>
  );
}

// The Jinja macros carried an `attrs` string to smuggle in maxlength/min/step. Those are just
// props here, so the escape hatch is gone and the constraints are typechecked.
type FieldProps = { label: ReactNode } & Omit<ComponentPropsWithoutRef<"input">, "className">;

export function Field({ label, ...rest }: FieldProps) {
  return (
    <Wrapper label={label}>
      <input className={INPUT} {...rest} />
    </Wrapper>
  );
}

type SelectFieldProps = {
  label: ReactNode;
  options: ReadonlyArray<{ value: string | number; text: string }>;
} & Omit<ComponentPropsWithoutRef<"select">, "className" | "children">;

export function SelectField({ label, options, ...rest }: SelectFieldProps) {
  return (
    <Wrapper label={label}>
      <select className={INPUT} {...rest}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.text}
          </option>
        ))}
      </select>
    </Wrapper>
  );
}

type TextareaFieldProps = { label: ReactNode } & Omit<
  ComponentPropsWithoutRef<"textarea">,
  "className"
>;

export function TextareaField({ label, rows = 4, ...rest }: TextareaFieldProps) {
  return (
    <Wrapper label={label}>
      <textarea className={cn(INPUT)} rows={rows} {...rest} />
    </Wrapper>
  );
}
