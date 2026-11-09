// Renders public/icons/logo.svg into the PNG and ICO files the manifest,
// browsers and phones ask for. Run with `npm run icons` after changing the logo.
// Needs Playwright with Chromium (only for this script, not for the app).
import { createRequire } from "node:module";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const here = dirname(fileURLToPath(import.meta.url));
const publicDir = join(here, "..", "public");
const iconsDir = join(publicDir, "icons");
const svg = readFileSync(join(iconsDir, "logo.svg"), "utf8");
const svgUrl = `data:image/svg+xml;base64,${Buffer.from(svg).toString("base64")}`;
const ACCENT = "#4338CA";

async function render(page, size, { maskable = false } = {}) {
  await page.setViewportSize({ width: size, height: size });
  // A maskable icon fills the whole square; launchers crop it to their own shape,
  // so the logo sits inside the middle 70%.
  const inner = maskable ? Math.round(size * 0.7) : size;
  await page.setContent(
    `<html><body style="margin:0;width:${size}px;height:${size}px;display:grid;place-items:center;` +
      `background:${maskable ? ACCENT : "transparent"}">` +
      `<img src="${svgUrl}" width="${inner}" height="${inner}"></body></html>`,
  );
  return page.screenshot({ omitBackground: !maskable, type: "png" });
}

// ICO files can hold PNG images directly (Vista and later, every current browser).
function ico(images) {
  const header = Buffer.alloc(6);
  header.writeUInt16LE(0, 0);
  header.writeUInt16LE(1, 2);
  header.writeUInt16LE(images.length, 4);
  const entries = [];
  let offset = 6 + images.length * 16;
  for (const { size, data } of images) {
    const entry = Buffer.alloc(16);
    entry.writeUInt8(size >= 256 ? 0 : size, 0);
    entry.writeUInt8(size >= 256 ? 0 : size, 1);
    entry.writeUInt16LE(1, 4);
    entry.writeUInt16LE(32, 6);
    entry.writeUInt32LE(data.length, 8);
    entry.writeUInt32LE(offset, 12);
    offset += data.length;
    entries.push(entry);
  }
  return Buffer.concat([header, ...entries, ...images.map((i) => i.data)]);
}

const browser = await chromium.launch();
const page = await browser.newPage({ deviceScaleFactor: 1 });
for (const size of [32, 192, 512]) {
  writeFileSync(join(iconsDir, `icon-${size}.png`), await render(page, size));
}
writeFileSync(join(iconsDir, "maskable-512.png"), await render(page, 512, { maskable: true }));
writeFileSync(join(iconsDir, "apple-touch-icon.png"), await render(page, 180, { maskable: true }));
const small = [];
for (const size of [16, 32, 48]) small.push({ size, data: await render(page, size) });
writeFileSync(join(publicDir, "favicon.ico"), ico(small));
await browser.close();
