import { render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { HeroMark } from "@/components/hero/hero-mark";
import { MARK } from "@/components/hero/hero-mark-data";

type Hooks = { onReady: () => void; onError: () => void };

const mountLebanonScene =
  vi.fn<(canvas: HTMLCanvasElement, hooks: Hooks) => (() => void) | null>();

vi.mock("@/components/hero/lebanon-scene", () => ({
  mountLebanonScene: (canvas: HTMLCanvasElement, hooks: Hooks) =>
    mountLebanonScene(canvas, hooks),
}));

afterEach(() => {
  mountLebanonScene.mockReset();
});

const staticMark = (container: HTMLElement) =>
  container.querySelector(`svg path[d="${MARK.path}"]`);

describe("HeroMark", () => {
  it("draws the static word when WebGL is unavailable", async () => {
    mountLebanonScene.mockReturnValue(null);

    const { container } = render(<HeroMark />);

    await waitFor(() => expect(staticMark(container)).not.toBeNull());
    expect(container.querySelector("canvas")).toHaveAttribute("data-status", "fallback");
  });

  it("falls back when the relief fails to load", async () => {
    mountLebanonScene.mockImplementation((_, { onError }) => {
      queueMicrotask(onError);
      return () => {};
    });

    const { container } = render(<HeroMark />);

    await waitFor(() => expect(staticMark(container)).not.toBeNull());
  });

  it("shows the canvas once the first frame renders and disposes on unmount", async () => {
    const dispose = vi.fn();
    mountLebanonScene.mockImplementation((_, { onReady }) => {
      queueMicrotask(onReady);
      return dispose;
    });

    const { container, unmount } = render(<HeroMark />);
    const canvas = container.querySelector("canvas")!;

    await waitFor(() => expect(canvas).toHaveAttribute("data-status", "ready"));
    expect(canvas).toHaveClass("opacity-100");
    expect(staticMark(container)).toBeNull();

    unmount();
    expect(dispose).toHaveBeenCalledOnce();
  });
});
