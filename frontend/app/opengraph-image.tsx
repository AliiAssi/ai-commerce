import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { ImageResponse } from "next/og";

import { OPEN_GRAPH_DEFAULTS, SITE_URL } from "@/lib/seo";
import { HERO_LINES, STORE_NAME } from "@/lib/store";

export const alt = OPEN_GRAPH_DEFAULTS.images[0].alt;
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const SHELVES = "Olive oil · Za'atar · Soap · Ceramics · Cedar woodwork";

async function palette() {
  const css = await readFile(join(process.cwd(), "styles/tokens.css"), "utf8");
  const color = (token: string) => {
    const match = css.match(new RegExp(`--c-${token}:\\s*(\\d+) (\\d+) (\\d+)`));
    if (!match) throw new Error(`opengraph-image: --c-${token} is missing from tokens.css`);
    return `rgb(${match[1]}, ${match[2]}, ${match[3]})`;
  };
  return {
    surface: color("surface"),
    brand: color("brand"),
    ink: color("ink"),
    muted: color("ink-muted"),
    border: color("border"),
  };
}

// Satori cannot read the site's woff2 files, so the serif is fetched as TTF, subset to the
// glyphs on the card. Without the network the card still renders, in the default face.
async function serif(text: string): Promise<ArrayBuffer | null> {
  try {
    const css = await fetch(
      `https://fonts.googleapis.com/css2?family=Newsreader&text=${encodeURIComponent(text)}`,
    ).then((response) => response.text());
    const url = css.match(/src: url\((.+?)\) format\('(?:opentype|truetype)'\)/)?.[1];
    return url ? await fetch(url).then((response) => response.arrayBuffer()) : null;
  } catch {
    return null;
  }
}

export default async function OpenGraphImage() {
  const host = new URL(SITE_URL).host;
  const headline = HERO_LINES.join(" ");
  const [colors, logo, font] = await Promise.all([
    palette(),
    readFile(join(process.cwd(), "public/img/assistant.png"), "base64"),
    serif(`${STORE_NAME}${headline}${SHELVES}${host}`),
  ]);

  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        padding: "72px 80px",
        background: colors.surface,
        color: colors.ink,
        fontFamily: font ? "Newsreader" : undefined,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 28 }}>
        <img
          src={`data:image/png;base64,${logo}`}
          width={96}
          height={96}
          alt=""
          style={{ borderRadius: 48 }}
        />
        <div style={{ fontSize: 44, letterSpacing: 14 }}>{STORE_NAME}</div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
        <div style={{ width: 96, height: 6, background: colors.brand }} />
        <div
          style={{ display: "flex", flexDirection: "column", fontSize: 80, lineHeight: 1.05 }}
        >
          {HERO_LINES.map((line) => (
            <span key={line}>{line}</span>
          ))}
        </div>
      </div>

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          borderTop: `2px solid ${colors.border}`,
          paddingTop: 28,
          fontSize: 30,
          color: colors.muted,
        }}
      >
        <span>{SHELVES}</span>
        <span>{host}</span>
      </div>
    </div>,
    {
      ...size,
      fonts: font ? [{ name: "Newsreader", data: font, style: "normal", weight: 400 }] : [],
    },
  );
}
