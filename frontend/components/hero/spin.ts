const TURN = Math.PI * 2;
const STIFFNESS = 7;
const DAMPING = 4.2;
const YAW_PER_WIDTH = Math.PI * 1.2;
const PITCH_PER_HEIGHT = 0.9;
const PITCH_MIN = -0.5;
const PITCH_MAX = 0.45;
const STALE_MS = 80;
const REST = 1e-3;

/**
 * Drag-to-spin for the hero model: a turntable that follows the pointer while held, then
 * springs back to face the front, finishing a hard flick on the nearest full turn.
 */
export function createSpin() {
  let yaw = 0;
  let pitch = 0;
  let vYaw = 0;
  let vPitch = 0;
  let target = 0;
  let held = false;
  let lastMove = 0;

  const resting = () =>
    !held &&
    Math.abs(yaw - target) < REST &&
    Math.abs(pitch) < REST &&
    Math.abs(vYaw) < REST &&
    Math.abs(vPitch) < REST;

  return {
    get yaw() {
      return yaw;
    },
    get pitch() {
      return pitch;
    },
    get held() {
      return held;
    },
    resting,

    grab(timeMs: number) {
      held = true;
      vYaw = 0;
      vPitch = 0;
      lastMove = timeMs;
    },

    drag(dx: number, dy: number, width: number, height: number, timeMs: number) {
      if (!held) return;
      const dYaw = (dx / Math.max(width, 1)) * YAW_PER_WIDTH;
      const nextPitch = Math.min(
        PITCH_MAX,
        Math.max(PITCH_MIN, pitch + (dy / Math.max(height, 1)) * PITCH_PER_HEIGHT),
      );
      const dt = Math.max((timeMs - lastMove) / 1000, 1 / 240);
      vYaw = vYaw * 0.5 + (dYaw / dt) * 0.5;
      vPitch = vPitch * 0.5 + ((nextPitch - pitch) / dt) * 0.5;
      yaw += dYaw;
      pitch = nextPitch;
      lastMove = timeMs;
    },

    release(timeMs: number, instant: boolean) {
      if (!held) return;
      held = false;
      if (timeMs - lastMove > STALE_MS) {
        vYaw = 0;
        vPitch = 0;
      }
      target = Math.round((yaw + vYaw / DAMPING) / TURN) * TURN;
      if (instant) {
        yaw = 0;
        target = 0;
        pitch = 0;
        vYaw = 0;
        vPitch = 0;
      }
    },

    step(dt: number) {
      if (held || dt <= 0) return;
      vYaw += (-(yaw - target) * STIFFNESS - vYaw * DAMPING) * dt;
      yaw += vYaw * dt;
      vPitch += (-pitch * STIFFNESS - vPitch * DAMPING) * dt;
      pitch += vPitch * dt;
      if (resting()) {
        yaw = 0;
        target = 0;
        pitch = 0;
        vYaw = 0;
        vPitch = 0;
      }
    },
  };
}

export type Spin = ReturnType<typeof createSpin>;
