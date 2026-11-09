import { describe, expect, it } from "vitest";

import { createSpin } from "@/components/hero/spin";

const TURN = Math.PI * 2;

function settle(spin: ReturnType<typeof createSpin>, seconds = 6) {
  for (let t = 0; t < seconds; t += 1 / 60) spin.step(1 / 60);
}

describe("createSpin", () => {
  it("follows the pointer while held", () => {
    const spin = createSpin();
    spin.grab(0);
    spin.drag(500, 0, 1000, 500, 16);

    expect(spin.yaw).toBeCloseTo(Math.PI * 0.6);
    settle(spin);
    expect(spin.yaw).toBeCloseTo(Math.PI * 0.6);
  });

  it("glides back to face the front after a slow drag", () => {
    const spin = createSpin();
    spin.grab(0);
    spin.drag(200, 100, 1000, 500, 16);
    spin.release(500, false);

    settle(spin);
    expect(spin.yaw).toBe(0);
    expect(spin.pitch).toBe(0);
    expect(spin.resting()).toBe(true);
  });

  it("finishes a hard flick on the nearest full turn instead of unwinding", () => {
    const spin = createSpin();
    spin.grab(0);
    for (let i = 1; i <= 6; i++) spin.drag(400, 0, 1000, 500, i * 16);
    spin.release(6 * 16 + 5, false);

    const peaks: number[] = [];
    for (let t = 0; t < 6; t += 1 / 60) {
      spin.step(1 / 60);
      peaks.push(spin.yaw);
    }
    expect(Math.max(...peaks)).toBeGreaterThan(TURN * 0.75);
    expect(spin.resting()).toBe(true);
  });

  it("keeps the tilt within limits", () => {
    const spin = createSpin();
    spin.grab(0);
    spin.drag(0, 5000, 1000, 500, 16);
    expect(spin.pitch).toBeLessThanOrEqual(0.45);
    spin.drag(0, -10000, 1000, 500, 32);
    expect(spin.pitch).toBeGreaterThanOrEqual(-0.5);
  });

  it("snaps straight back when motion is reduced", () => {
    const spin = createSpin();
    spin.grab(0);
    spin.drag(300, 50, 1000, 500, 16);
    spin.release(20, true);

    expect(spin.yaw).toBe(0);
    expect(spin.pitch).toBe(0);
    expect(spin.resting()).toBe(true);
  });
});
