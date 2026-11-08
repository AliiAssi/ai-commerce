# /// script
# requires-python = ">=3.12"
# dependencies = ["fonttools>=4.50", "uharfbuzz>=0.40", "freetype-py>=2.4", "numpy>=2", "scipy>=1.13", "pillow>=10"]
# ///
"""Bake the homepage mark: Lebanon's relief and بيت floating over it.

    uv run frontend/scripts/bake_hero_mark.py

Writes public/img/hero-relief.png (R elevation, G inside the border, B the word's soft shadow)
and components/hero/hero-mark-data.ts (relief size, the shaped word outline and where it sits).
"""

import json
import math
import tempfile
import urllib.request
from pathlib import Path

import numpy as np
import uharfbuzz as hb
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.freetypePen import FreeTypePen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.svgLib.path import parse_path
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from PIL import Image, ImageDraw
from scipy.ndimage import binary_erosion, distance_transform_edt, gaussian_filter

FRONTEND = Path(__file__).resolve().parent.parent
PNG_OUT = FRONTEND / "public/img/hero-relief.png"
TS_OUT = FRONTEND / "components/hero/hero-mark-data.ts"
CACHE = Path(tempfile.gettempdir()) / "beit-hero-mark"

WORD = "بيت"
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/reemkufi/ReemKufi%5Bwght%5D.ttf"
FONT_AXES = {"wght": 700}
BORDER_URL = (
    "https://github.com/wmgeolab/geoBoundaries/raw/90a1d52/"
    "releaseData/gbOpen/LBN/ADM0/geoBoundaries-LBN-ADM0.geojson"
)
TILE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
ZOOM, TOP_METRES, WIDTH, MARGIN, SUPERSAMPLE = 9, 3100.0, 640, 0.05, 4
WORD_MARGIN_PX, WORD_SHRINK, SHADOW_BLUR_PX = 6, 0.84, 7


def fetch(url: str, name: str) -> Path:
    path = CACHE / name
    if not path.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "beit-hero-bake"})
        with urllib.request.urlopen(req) as res:
            path.write_bytes(res.read())
    return path


def shaped_word() -> tuple[str, tuple[float, float, float, float]]:
    """HarfBuzz-shaped outline in 1000 units per em, y down, and its bounds."""
    font = TTFont(fetch(FONT_URL, "font.ttf"))
    if FONT_AXES:
        font = instantiateVariableFont(font, FONT_AXES)
    static = CACHE / "font-static.ttf"
    font.save(static)
    hb_font = hb.Font(hb.Face(hb.Blob.from_file_path(str(static))))
    buf = hb.Buffer()
    buf.add_str(WORD)
    buf.guess_segment_properties()
    hb.shape(hb_font, buf, {})

    font = TTFont(static)
    order, glyphs = font.getGlyphOrder(), font.getGlyphSet()
    scale = 1000 / font["head"].unitsPerEm
    svg = SVGPathPen(glyphs, ntos=lambda v: f"{v:.1f}".rstrip("0").rstrip("."))
    bounds = BoundsPen(glyphs)
    x = 0
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        t = (scale, 0, 0, -scale, (x + pos.x_offset) * scale, -pos.y_offset * scale)
        glyphs[order[info.codepoint]].draw(TransformPen(svg, t))
        glyphs[order[info.codepoint]].draw(TransformPen(bounds, t))
        x += pos.x_advance
    return svg.getCommands(), tuple(round(v, 1) for v in bounds.bounds)


def relief():
    """Elevation and border mask on a grid turned to the coast and rotated 180°, never mirrored."""
    ring = np.array(
        json.loads(fetch(BORDER_URL, "border.geojson").read_text())["features"][0]["geometry"][
            "coordinates"
        ][0]
    )
    lon0, lat0 = ring[:, 0].mean(), ring[:, 1].mean()
    kx, ky = 111.32 * math.cos(math.radians(lat0)), 110.57
    pts = np.stack([(ring[:, 0] - lon0) * kx, (ring[:, 1] - lat0) * ky], 1)
    evals, evecs = np.linalg.eigh(np.cov(pts.T))
    a = evecs[:, np.argmax(evals)]
    a = a if a[1] > 0 else -a
    n = np.array([a[1], -a[0]])
    s, t = -(pts @ a), -(pts @ n)
    k = (s.max() - s.min()) / (WIDTH * (1 - 2 * MARGIN))
    height = int(math.ceil((t.max() - t.min()) / k / (1 - 2 * MARGIN * 2.2)))
    s_min = s.min() - MARGIN * WIDTH * k
    t_min = t.min() - (height * k - (t.max() - t.min())) / 2

    def tile_xy(lon, lat):
        n_px = 2**ZOOM * 256
        r = np.radians(lat)
        return (lon + 180) / 360 * n_px, (1 - np.log(np.tan(r) + 1 / np.cos(r)) / np.pi) / 2 * n_px

    ii, rr = np.meshgrid(np.arange(WIDTH) + 0.5, np.arange(height) + 0.5)
    p = -((s_min + ii * k)[..., None] * a + (t_min + rr * k)[..., None] * n)
    px, py = tile_xy(lon0 + p[..., 0] / kx, lat0 + p[..., 1] / ky)
    tx0, ty0 = int(px.min() // 256), int(py.min() // 256)
    tx1, ty1 = int(px.max() // 256), int(py.max() // 256)
    mosaic = np.zeros(((ty1 - ty0 + 1) * 256, (tx1 - tx0 + 1) * 256), np.float32)
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            rgb = np.asarray(
                Image.open(fetch(TILE_URL.format(z=ZOOM, x=tx, y=ty), f"{ZOOM}_{tx}_{ty}.png")).convert(
                    "RGB"
                ),
                np.float32,
            )
            mosaic[(ty - ty0) * 256 : (ty - ty0 + 1) * 256, (tx - tx0) * 256 : (tx - tx0 + 1) * 256] = (
                rgb[..., 0] * 256 + rgb[..., 1] + rgb[..., 2] / 256 - 32768
            )
    fx, fy = px - tx0 * 256, py - ty0 * 256
    x0, y0 = np.floor(fx).astype(int), np.floor(fy).astype(int)
    wx, wy = fx - x0, fy - y0
    elev = (
        mosaic[y0, x0] * (1 - wx) * (1 - wy)
        + mosaic[y0, x0 + 1] * wx * (1 - wy)
        + mosaic[y0 + 1, x0] * (1 - wx) * wy
        + mosaic[y0 + 1, x0 + 1] * wx * wy
    ).clip(0, None)

    big = Image.new("L", (WIDTH * SUPERSAMPLE, height * SUPERSAMPLE), 0)
    poly = [((si - s_min) / k * SUPERSAMPLE, (ti - t_min) / k * SUPERSAMPLE) for si, ti in zip(s, t)]
    ImageDraw.Draw(big).polygon(poly, fill=255)
    land = np.asarray(big.resize((WIDTH, height), Image.LANCZOS), np.float32) / 255
    elev = gaussian_filter(elev * (land > 0.02), 1.8)
    return elev[::-1, ::-1], land[::-1, ::-1]


def word_mask(path: str, box, cx: float, cy: float, glyph_h: float, w: int, h: int) -> np.ndarray:
    """The word drawn into the relief grid with its bounds centred on (cx, cy), y down."""
    x0, y0, x1, y1 = box
    scale = glyph_h / (y1 - y0)
    ox, oy = cx - (x0 + x1) / 2 * scale, cy - (y0 + y1) / 2 * scale
    pen = FreeTypePen(None)
    parse_path(path, TransformPen(pen, (scale, 0, 0, -scale, ox, h - oy)))
    return pen.array(width=w, height=h)


def fit_word(path: str, box, land: np.ndarray):
    """Largest word whose footprint stays inside the border, then nudged toward the middle."""
    h, w = land.shape
    inside = distance_transform_edt(land > 0.5) >= WORD_MARGIN_PX

    def place(glyph_h: float):
        shape = word_mask(path, box, w / 2, h / 2, glyph_h, w, h) > 0.5
        ys, xs = np.nonzero(shape)
        if not len(xs) or xs.min() == 0 or ys.min() == 0 or xs.max() == w - 1 or ys.max() == h - 1:
            return None
        structure = shape[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
        oy, ox = np.nonzero(binary_erosion(inside, structure=structure, border_value=0))
        if not len(ox):
            return None
        # erosion reports where the structure's middle pixel lands; move the drawn centre with it
        cx = w / 2 + ox - (xs.min() + structure.shape[1] // 2)
        cy = h / 2 + oy - (ys.min() + structure.shape[0] // 2)
        best = int(np.argmin(np.abs(cx - w / 2) + np.abs(cy - h / 2) * 0.5))
        return float(cx[best]), float(cy[best])

    lo, hi = 8.0, float(h)
    while hi - lo > 1.5:
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if place(mid) else (lo, mid)
    glyph_h = lo * WORD_SHRINK
    cx, cy = place(glyph_h)
    return cx, cy, glyph_h


def main() -> None:
    path, box = shaped_word()
    elev, land = relief()
    h, w = land.shape
    cx, cy, glyph_h = fit_word(path, box, land)
    shadow = gaussian_filter(word_mask(path, box, cx, cy, glyph_h, w, h), SHADOW_BLUR_PX)

    rgb = np.stack(
        [(elev / TOP_METRES * 255).clip(0, 255), land * 255, shadow.clip(0, 1) * 255], -1
    ).round()
    PNG_OUT.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb.astype(np.uint8), "RGB").save(PNG_OUT, optimize=True)

    TS_OUT.parent.mkdir(parents=True, exist_ok=True)
    TS_OUT.write_text(
        "// Generated by scripts/bake_hero_mark.py from Reem Kufi, Terrain Tiles and geoBoundaries.\n"
        "// Do not edit by hand; rerun the script.\n"
        "\n"
        "export const RELIEF = {\n"
        '  src: "/img/hero-relief.png",\n'
        f"  width: {w},\n"
        f"  height: {h},\n"
        f"  topMetres: {TOP_METRES:g},\n"
        "} as const;\n"
        "\n"
        "export const MARK = {\n"
        f'  path: "{path}",\n'
        f"  box: [{', '.join(f'{v:g}' for v in box)}],\n"
        f"  centerX: {cx:.1f},\n"
        f"  centerY: {cy:.1f},\n"
        f"  height: {glyph_h:.1f},\n"
        "} as const;\n"
    )
    print(f"{PNG_OUT.relative_to(FRONTEND)}  {PNG_OUT.stat().st_size // 1024} KB  {w}x{h}")
    print(f"{TS_OUT.relative_to(FRONTEND)}  word at ({cx:.0f}, {cy:.0f}), {glyph_h:.0f}px tall")


if __name__ == "__main__":
    main()
