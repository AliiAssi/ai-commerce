import {
  Color,
  DirectionalLight,
  ExtrudeGeometry,
  HemisphereLight,
  LinearFilter,
  MathUtils,
  Mesh,
  MeshStandardMaterial,
  NoColorSpace,
  PerspectiveCamera,
  PlaneGeometry,
  Scene,
  ShaderMaterial,
  SRGBColorSpace,
  TextureLoader,
  Vector2,
  Vector3,
  WebGLRenderer,
  type Texture,
} from "three";
import { SVGLoader } from "three/addons/loaders/SVGLoader.js";

import { MARK, RELIEF } from "@/components/hero/hero-mark-data";
import { createSpin } from "@/components/hero/spin";

type Mix = readonly [token: string, toward?: string, amount?: number];
type Part =
  | "ground"
  | "low"
  | "high"
  | "snow"
  | "cut"
  | "olive"
  | "cedar"
  | "wordFace"
  | "wordSide"
  | "fill";

const PALETTE: Record<Part, { light: Mix; dark: Mix }> = {
  ground: { light: ["--c-surface-alt"], dark: ["--c-surface-alt"] },
  low: { light: ["--c-sunk"], dark: ["--c-surface", "--c-ink-muted", 0.18] },
  high: { light: ["--c-surface"], dark: ["--c-surface", "--c-ink-muted", 0.5] },
  snow: { light: ["--c-surface"], dark: ["--c-ink", "--c-surface", 0.5] },
  cut: { light: ["--c-ink-faint", "--c-sunk", 0.3], dark: ["--c-sunk"] },
  olive: { light: ["--c-brand", "--c-ink-faint", 0.45], dark: ["--c-brand", "--c-sunk", 0.5] },
  cedar: { light: ["--c-brand", "--c-ink", 0.3], dark: ["--c-brand", "--c-sunk", 0.38] },
  wordFace: { light: ["--c-brand"], dark: ["--c-brand"] },
  wordSide: { light: ["--c-brand", "--c-ink", 0.35], dark: ["--c-brand", "--c-sunk", 0.45] },
  fill: { light: ["--c-ink-faint", "--c-border", 0.5], dark: ["--c-surface"] },
};

const WIDTH = 4;
const DEPTH = (WIDTH * RELIEF.height) / RELIEF.width;
const AMP = 0.3;
const BASE = 0.05;
const HOVER = 0.11;
const SNOW_LINE_M = 2400;
const OLIVE_TOP_M = 1150;
const CEDAR_BAND_M = [1200, 2000] as const;
const INTRO_S = 2.4;
const FOV = 30;
const LIGHT = new Vector3(-0.55, 0.78, -0.25).normalize();
const TARGET = new Vector3(0, 0.2, 0);

const easeOut = (t: number) => 1 - Math.pow(1 - MathUtils.clamp(t, 0, 1), 3);
const easeInOut = (t: number) => {
  const x = MathUtils.clamp(t, 0, 1);
  return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
};

function readPalette(): Record<Part, Color> {
  const style = getComputedStyle(document.documentElement);
  const token = (name: string) => {
    const [r, g, b] = style.getPropertyValue(name).trim().split(/\s+/).map(Number);
    return new Color().setRGB(r / 255, g / 255, b / 255, SRGBColorSpace);
  };
  const dark = token("--c-surface-alt").r < 0.2;
  const out = {} as Record<Part, Color>;
  for (const part of Object.keys(PALETTE) as Part[]) {
    const [base, toward, amount = 0] = PALETTE[part][dark ? "dark" : "light"];
    out[part] = toward ? token(base).lerp(token(toward), amount) : token(base);
  }
  return out;
}

function wordGeometry() {
  const [, y0, , y1] = MARK.box;
  const h = y1 - y0;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg"><g transform="scale(${1 / h},${-1 / h})"><path d="${MARK.path}"/></g></svg>`;
  const shapes = new SVGLoader().parse(svg).paths.flatMap((p) => SVGLoader.createShapes(p));
  const geometry = new ExtrudeGeometry(shapes, {
    depth: 0.11,
    bevelEnabled: true,
    bevelThickness: 0.02,
    bevelSize: 0.012,
    bevelSegments: 6,
    curveSegments: 14,
  });
  geometry.center();
  geometry.rotateX(-Math.PI / 2);
  return geometry;
}

const VERTEX = /* glsl */ `
  uniform sampler2D uRelief; uniform vec2 uTexel, uSize; uniform float uLift, uAmp, uBase;
  varying vec3 vPos; varying vec3 vN; varying float vH; varying vec2 vUv;
  float lifted(vec2 uv){ vec4 t = texture2D(uRelief, uv); return (t.r * uLift + uBase * smoothstep(.35, .65, t.g)) * uAmp; }
  void main(){
    vUv = uv;
    vH = texture2D(uRelief, uv).r * uLift;
    vec3 p = position; p.y += lifted(uv);
    float hl = lifted(uv - vec2(uTexel.x, 0.)), hr = lifted(uv + vec2(uTexel.x, 0.));
    float hf = lifted(uv + vec2(0., uTexel.y)), hb = lifted(uv - vec2(0., uTexel.y));
    vN = normalize(vec3(-(hr - hl) / (2. * uTexel.x * uSize.x), 1., -(hb - hf) / (2. * uTexel.y * uSize.y)));
    vec4 wp = modelMatrix * vec4(p, 1.);
    vPos = wp.xyz;
    gl_Position = projectionMatrix * viewMatrix * wp;
  }`;

const FRAGMENT = /* glsl */ `
  uniform sampler2D uRelief;
  uniform vec3 uLight, uGround, uLow, uHigh, uSnow, uCut, uOlive, uCedar;
  uniform float uLift, uOliveTop, uSnowLine, uShadow; uniform vec2 uCedarBand, uShadowOff;
  varying vec3 vPos; varying vec3 vN; varying float vH; varying vec2 vUv;
  float hash12(vec2 p){ vec3 p3 = fract(vec3(p.xyx) * .1031); p3 += dot(p3, p3.yzx + 33.33); return fract((p3.x + p3.y) * p3.z); }
  void main(){
    vec3 N = normalize(vN);
    float diff = max(dot(N, uLight), 0.);
    float steep = 1. - smoothstep(.55, .9, N.y);
    float rel = vH / max(uLift, 1e-3);

    vec3 c = mix(uLow, uHigh, smoothstep(0., .75, rel));
    c = mix(c, uSnow, smoothstep(uSnowLine, uSnowLine + .08, rel));
    c = mix(c, uCut, 1. - smoothstep(.15, .4, N.y));

    vec2 g = vPos.xz * 30.; vec2 id = floor(g); vec2 f = fract(g) - .5;
    vec2 q = f + (vec2(hash12(id + 3.), hash12(id + 7.)) - .5) * .4;
    float ground = 1. - steep;
    float olive = (1. - smoothstep(.09, .14, length(q))) * step(.7, hash12(id))
      * smoothstep(.01, .03, rel) * (1. - smoothstep(uOliveTop - .03, uOliveTop, rel));
    vec2 t = vec2(q.x, -q.y);
    float tri = max(-.1 - t.y, t.y - (.15 - abs(t.x) * 2.2));
    float cedar = (1. - smoothstep(0., .025, tri)) * step(.6, hash12(id + 11.))
      * smoothstep(uCedarBand.x - .02, uCedarBand.x, rel) * (1. - smoothstep(uCedarBand.y, uCedarBand.y + .02, rel));
    c = mix(c, uOlive, olive * ground * .9);
    c = mix(c, uCedar, cedar * ground);
    c *= .5 + .62 * diff;
    c *= 1. - texture2D(uRelief, vUv - uShadowOff).b * uShadow;

    vec3 col = mix(uGround, c, smoothstep(.0015, .004, vPos.y));
    float e = min(min(vUv.x, 1. - vUv.x), min(vUv.y, 1. - vUv.y));
    gl_FragColor = vec4(mix(uGround, col, smoothstep(0., .1, e)), 1.);
    #include <colorspace_fragment>
  }`;

/**
 * Mounts the relief-and-word scene on `canvas`. Returns a disposer, or null when WebGL is
 * unavailable so the caller can show the static mark instead.
 */
export function mountLebanonScene(
  canvas: HTMLCanvasElement,
  { onReady, onError }: { onReady: () => void; onError: () => void },
): (() => void) | null {
  let renderer: WebGLRenderer;
  try {
    renderer = new WebGLRenderer({
      canvas,
      antialias: true,
      powerPreference: "high-performance",
    });
  } catch {
    return null;
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

  const scene = new Scene();
  const camera = new PerspectiveCamera(FOV, 1, 0.1, 60);
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  const darkScheme = window.matchMedia("(prefers-color-scheme: dark)");
  let palette = readPalette();

  const fine = canvas.clientWidth >= 900;
  const land = new PlaneGeometry(
    WIDTH,
    DEPTH,
    fine ? RELIEF.width - 1 : RELIEF.width / 2,
    fine ? RELIEF.height - 1 : Math.round(RELIEF.height / 2),
  );
  land.rotateX(-Math.PI / 2);
  const relief = new ShaderMaterial({
    vertexShader: VERTEX,
    fragmentShader: FRAGMENT,
    uniforms: {
      uRelief: { value: null },
      uTexel: { value: new Vector2(1 / RELIEF.width, 1 / RELIEF.height) },
      uSize: { value: new Vector2(WIDTH, DEPTH) },
      uLift: { value: 0 },
      uAmp: { value: AMP },
      uBase: { value: BASE },
      uLight: { value: LIGHT },
      uShadowOff: { value: new Vector2() },
      uShadow: { value: 0 },
      uOliveTop: { value: OLIVE_TOP_M / RELIEF.topMetres },
      uSnowLine: { value: SNOW_LINE_M / RELIEF.topMetres },
      uCedarBand: { value: new Vector2(...CEDAR_BAND_M).divideScalar(RELIEF.topMetres) },
      uGround: { value: new Color() },
      uLow: { value: new Color() },
      uHigh: { value: new Color() },
      uSnow: { value: new Color() },
      uCut: { value: new Color() },
      uOlive: { value: new Color() },
      uCedar: { value: new Color() },
    },
  });
  scene.add(new Mesh(land, relief));

  const face = new MeshStandardMaterial({ roughness: 0.55 });
  const side = new MeshStandardMaterial({ roughness: 0.7 });
  const word = new Mesh(wordGeometry(), [face, side]);
  word.scale.setScalar((MARK.height / RELIEF.height) * DEPTH);
  const home = new Vector3(
    (MARK.centerX / RELIEF.width - 0.5) * WIDTH,
    AMP * (1 + BASE) + HOVER,
    (MARK.centerY / RELIEF.height - 0.5) * DEPTH,
  );
  word.position.copy(home);
  const sun = new DirectionalLight(0xffffff, 2.3);
  sun.position.copy(LIGHT).multiplyScalar(5);
  const sky = new HemisphereLight(0xffffff, 0xffffff, 1.2);
  scene.add(word, sun, sky);

  const applyPalette = () => {
    palette = readPalette();
    const u = relief.uniforms;
    scene.background = palette.ground;
    u.uGround.value.copy(palette.ground);
    u.uLow.value.copy(palette.low);
    u.uHigh.value.copy(palette.high);
    u.uSnow.value.copy(palette.snow);
    u.uCut.value.copy(palette.cut);
    u.uOlive.value.copy(palette.olive);
    u.uCedar.value.copy(palette.cedar);
    face.color.copy(palette.wordFace);
    side.color.copy(palette.wordSide);
    sky.groundColor.copy(palette.fill);
  };
  applyPalette();

  let dist = 5;
  const fit = () => {
    const w = Math.max(1, canvas.clientWidth);
    const h = Math.max(1, canvas.clientHeight);
    renderer.setSize(w, h, false);
    const style = getComputedStyle(canvas);
    const offset = parseFloat(style.getPropertyValue("--mark-offset")) || 0;
    const span = parseFloat(style.getPropertyValue("--mark-span")) || 0.9;
    camera.aspect = w / h;
    const tan = Math.tan(MathUtils.degToRad(FOV / 2));
    dist = Math.max(
      (WIDTH * 0.94) / (span * 2 * tan * camera.aspect),
      (DEPTH * 0.95) / (0.8 * 2 * tan),
    );
    if (offset) camera.setViewOffset(w, h, -w * offset, 0, w, h);
    else camera.clearViewOffset();
    camera.updateProjectionMatrix();
  };
  fit();

  const corners = [-1, 1].flatMap((sx) =>
    [-1, 1].flatMap((sz) =>
      [0, AMP * 1.2].map((y) => new Vector3((sx * WIDTH) / 2.2, y, (sz * DEPTH) / 2.4)),
    ),
  );
  const projected = new Vector3();
  const hit = { x0: 0, y0: 0, x1: 0, y1: 0 };
  const measureHit = () => {
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    hit.x0 = hit.y0 = Infinity;
    hit.x1 = hit.y1 = -Infinity;
    for (const corner of corners) {
      projected.copy(corner).project(camera);
      const x = ((projected.x + 1) / 2) * w;
      const y = ((1 - projected.y) / 2) * h;
      hit.x0 = Math.min(hit.x0, x);
      hit.x1 = Math.max(hit.x1, x);
      hit.y0 = Math.min(hit.y0, y);
      hit.y1 = Math.max(hit.y1, y);
    }
  };
  const local = (e: PointerEvent) => {
    const r = canvas.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top] as const;
  };
  const overModel = (e: PointerEvent) => {
    const [x, y] = local(e);
    return x >= hit.x0 && x <= hit.x1 && y >= hit.y0 && y <= hit.y1;
  };

  const pointer = { x: 0, y: 0, tx: 0, ty: 0 };
  const spin = createSpin();
  let dragId: number | null = null;
  let dragX = 0;
  let dragY = 0;
  const onDown = (e: PointerEvent) => {
    if (dragId !== null || e.button > 0 || !overModel(e)) return;
    if (e.pointerType === "mouse") e.preventDefault();
    dragId = e.pointerId;
    dragX = e.clientX;
    dragY = e.clientY;
    try {
      canvas.setPointerCapture(e.pointerId);
    } catch {
      // the pointer is already gone; the drag still ends on pointerup
    }
    canvas.style.cursor = "grabbing";
    pointer.tx = pointer.ty = 0;
    spin.grab(e.timeStamp);
    schedule();
  };
  const onDrag = (e: PointerEvent) => {
    if (e.pointerId !== dragId) {
      if (e.pointerType === "mouse") canvas.style.cursor = overModel(e) ? "grab" : "";
      return;
    }
    const dy = e.pointerType === "touch" ? 0 : e.clientY - dragY;
    spin.drag(e.clientX - dragX, dy, canvas.clientWidth, canvas.clientHeight, e.timeStamp);
    dragX = e.clientX;
    dragY = e.clientY;
    schedule();
  };
  const onUp = (e: PointerEvent) => {
    if (e.pointerId !== dragId) return;
    dragId = null;
    spin.release(e.timeStamp, reduced.matches);
    canvas.style.cursor = e.pointerType === "mouse" && overModel(e) ? "grab" : "";
    schedule();
  };

  const onPointer = (e: PointerEvent) => {
    if (reduced.matches || dragId !== null || e.pointerType !== "mouse") return;
    const r = canvas.getBoundingClientRect();
    const inside =
      e.clientX >= r.left &&
      e.clientX <= r.right &&
      e.clientY >= r.top &&
      e.clientY <= r.bottom;
    pointer.tx = inside ? ((e.clientX - r.left) / r.width) * 2 - 1 : 0;
    pointer.ty = inside ? -(((e.clientY - r.top) / r.height) * 2 - 1) : 0;
    schedule();
  };

  let ready = false;
  let visible = true;
  let raf = 0;
  let last = 0;
  let time = 0;
  let intro = reduced.matches ? INTRO_S * 2 : 0;
  let orbit = 0;
  let tilt = 0;

  function render(now: number) {
    raf = 0;
    const dt = last ? Math.min((now - last) / 1000, 0.05) : 0;
    last = now;
    const still = reduced.matches;
    const motion = still ? 0 : 1;
    if (still) intro = INTRO_S * 2;
    time += dt;
    intro += dt;

    const k = still ? 1 : 1 - Math.exp(-dt * 2.4);
    pointer.x += (pointer.tx * motion - pointer.x) * (still ? 1 : 1 - Math.exp(-dt * 6));
    pointer.y += (pointer.ty * motion - pointer.y) * (still ? 1 : 1 - Math.exp(-dt * 6));
    orbit += (pointer.x * 0.4 + Math.sin(time * 0.1) * 0.1 * motion - orbit) * k;
    tilt += (pointer.y * 0.12 - tilt) * k;
    spin.step(dt);
    const azimuth = orbit - spin.yaw;
    const el = MathUtils.clamp(
      0.92 + tilt + spin.pitch + (1 - easeOut(intro / INTRO_S)) * 0.3,
      0.3,
      1.45,
    );
    camera.position.set(
      TARGET.x + Math.sin(azimuth) * Math.cos(el) * dist,
      TARGET.y + Math.sin(el) * dist,
      TARGET.z + Math.cos(azimuth) * Math.cos(el) * dist,
    );
    camera.lookAt(TARGET);
    camera.updateMatrixWorld();
    measureHit();

    relief.uniforms.uLift.value = easeInOut(intro / INTRO_S);
    const settle = easeOut((intro - 0.6) / (INTRO_S - 0.2));
    const above =
      home.y - AMP * 0.45 + (1 - settle) * 0.5 + Math.sin(time * 0.9) * 0.012 * motion;
    word.position.y = above + AMP * 0.45;
    relief.uniforms.uShadowOff.value.set(
      ((-LIGHT.x / LIGHT.y) * above) / WIDTH,
      ((LIGHT.z / LIGHT.y) * above) / DEPTH,
    );
    relief.uniforms.uShadow.value = (palette.ground.r < 0.2 ? 0.5 : 0.42) * settle;

    renderer.render(scene, camera);
    if (!ready) {
      ready = true;
      onReady();
    }
    if (!still) schedule();
  }

  function schedule() {
    if (!raf && visible && !document.hidden && relief.uniforms.uRelief.value) {
      raf = requestAnimationFrame(render);
    }
  }

  const resize = new ResizeObserver(() => {
    fit();
    schedule();
  });
  const seen = new IntersectionObserver(([entry]) => {
    visible = entry.isIntersecting;
    last = 0;
    schedule();
  });
  const retheme = () => {
    applyPalette();
    schedule();
  };
  const themeAttr = new MutationObserver(retheme);
  const onVisibility = () => {
    last = 0;
    schedule();
  };

  let texture: Texture | null = null;
  let disposed = false;
  new TextureLoader()
    .loadAsync(RELIEF.src)
    .then((tex) => {
      if (disposed) return tex.dispose();
      tex.colorSpace = NoColorSpace;
      tex.minFilter = tex.magFilter = LinearFilter;
      tex.generateMipmaps = false;
      texture = tex;
      relief.uniforms.uRelief.value = tex;
      schedule();
    })
    .catch(() => {
      if (!disposed) onError();
    });

  resize.observe(canvas);
  seen.observe(canvas);
  themeAttr.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-theme"],
  });
  darkScheme.addEventListener("change", retheme);
  reduced.addEventListener("change", schedule);
  window.addEventListener("pointermove", onPointer, { passive: true });
  canvas.addEventListener("pointerdown", onDown);
  canvas.addEventListener("pointermove", onDrag);
  canvas.addEventListener("pointerup", onUp);
  canvas.addEventListener("pointercancel", onUp);
  canvas.addEventListener("lostpointercapture", onUp);
  document.addEventListener("visibilitychange", onVisibility);

  return () => {
    disposed = true;
    if (raf) cancelAnimationFrame(raf);
    resize.disconnect();
    seen.disconnect();
    themeAttr.disconnect();
    darkScheme.removeEventListener("change", retheme);
    reduced.removeEventListener("change", schedule);
    window.removeEventListener("pointermove", onPointer);
    canvas.removeEventListener("pointerdown", onDown);
    canvas.removeEventListener("pointermove", onDrag);
    canvas.removeEventListener("pointerup", onUp);
    canvas.removeEventListener("pointercancel", onUp);
    canvas.removeEventListener("lostpointercapture", onUp);
    canvas.style.cursor = "";
    document.removeEventListener("visibilitychange", onVisibility);
    land.dispose();
    word.geometry.dispose();
    relief.dispose();
    face.dispose();
    side.dispose();
    texture?.dispose();
    renderer.dispose();
  };
}
