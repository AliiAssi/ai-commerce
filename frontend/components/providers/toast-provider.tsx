"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import { Toast, type ToastVariant } from "@/components/ui/toast";

// Timings match armToast() in the Jinja app's app.js, so the feel is unchanged.
const DISMISS_AFTER_MS = 4200;
const LEAVE_MS = 260;

interface ToastItem {
  id: number;
  message: string;
  variant: ToastVariant;
  leaving: boolean;
}

type PushToast = (message: string, variant?: ToastVariant) => void;

const ToastContext = createContext<PushToast | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(0);
  const timers = useRef<Set<ReturnType<typeof setTimeout>>>(new Set());

  useEffect(() => {
    const pending = timers.current;
    return () => {
      pending.forEach(clearTimeout);
      pending.clear();
    };
  }, []);

  const push = useCallback<PushToast>((message, variant = "info") => {
    const id = nextId.current++;
    setToasts((current) => [...current, { id, message, variant, leaving: false }]);

    const startLeaving = setTimeout(() => {
      setToasts((current) => current.map((t) => (t.id === id ? { ...t, leaving: true } : t)));
      const remove = setTimeout(() => {
        setToasts((current) => current.filter((t) => t.id !== id));
        timers.current.delete(remove);
      }, LEAVE_MS);
      timers.current.add(remove);
      timers.current.delete(startLeaving);
    }, DISMISS_AFTER_MS);

    timers.current.add(startLeaving);
  }, []);

  return (
    <ToastContext.Provider value={push}>
      {children}
      {/* #toasts is positioned by app.css, ported unchanged from the Jinja stylesheet */}
      <div id="toasts">
        {toasts.map((toast) => (
          <Toast key={toast.id} variant={toast.variant} leaving={toast.leaving}>
            {toast.message}
          </Toast>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): PushToast {
  const push = useContext(ToastContext);
  if (!push) throw new Error("useToast must be used inside <ToastProvider>");
  return push;
}
