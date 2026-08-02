"use client";

import { useLinkStatus } from "next/link";
import type { ReactNode } from "react";

import { Spinner } from "./spinner";

/** Must be rendered inside a <Link>: useLinkStatus reads that link's own transition. */
export function LinkSpinner({ children = null }: { children?: ReactNode }) {
  const { pending } = useLinkStatus();
  return pending ? <Spinner /> : <>{children}</>;
}
