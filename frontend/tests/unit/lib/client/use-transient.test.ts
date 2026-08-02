import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useTransient } from "@/lib/client/use-transient";

describe("useTransient", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("is off until triggered, then turns itself off again", () => {
    const { result } = renderHook(() => useTransient(1000));
    expect(result.current[0]).toBe(false);

    act(() => result.current[1]());
    expect(result.current[0]).toBe(true);

    act(() => void vi.advanceTimersByTime(1000));
    expect(result.current[0]).toBe(false);
  });

  /** Two quick adds in a row should read as confirmed throughout, not blink at the first. */
  it("restarts the window rather than letting the first timer end it", () => {
    const { result } = renderHook(() => useTransient(1000));

    act(() => result.current[1]());
    act(() => void vi.advanceTimersByTime(800));
    act(() => result.current[1]());

    act(() => void vi.advanceTimersByTime(800));
    expect(result.current[0]).toBe(true);

    act(() => void vi.advanceTimersByTime(200));
    expect(result.current[0]).toBe(false);
  });

  it("drops its timer on unmount", () => {
    const { result, unmount } = renderHook(() => useTransient(1000));
    act(() => result.current[1]());
    unmount();
    expect(() => vi.advanceTimersByTime(2000)).not.toThrow();
  });
});
