// Draws one frame of a video maker intro onto a 16:9 canvas. The preview and
// the recording use the same function, so what you see is what's rendered.

export type TemplateId = "welcome" | "coming_soon" | "announcement" | "qr";

export interface Design {
  template: TemplateId;
  headline: string;
  subtext: string;
  qrText: string;
  background: string;
  textColour: string;
  accent: string;
  duration: number;
}

export interface Pictures {
  logo?: HTMLImageElement | null;
  backdrop?: HTMLImageElement | null;
  qr?: HTMLImageElement | null;
}

const ease = (x: number) => 1 - Math.pow(1 - Math.min(1, Math.max(0, x)), 3);

function fitText(ctx: CanvasRenderingContext2D, text: string, maxWidth: number, size: number, weight: number): number {
  let s = size;
  ctx.font = `${weight} ${s}px system-ui, "Segoe UI", Roboto, sans-serif`;
  while (s > 18 && ctx.measureText(text).width > maxWidth) {
    s -= 4;
    ctx.font = `${weight} ${s}px system-ui, "Segoe UI", Roboto, sans-serif`;
  }
  return s;
}

/** `t` is seconds since the start. */
export function drawFrame(ctx: CanvasRenderingContext2D, w: number, h: number, design: Design, pics: Pictures, t: number) {
  const d = Math.max(1, design.duration);
  const fadeIn = ease(t / 0.8);
  const fadeOut = 1 - ease((t - (d - 0.6)) / 0.6);
  const alpha = Math.min(fadeIn, fadeOut);
  const zoom = 1 + 0.04 * (t / d);

  ctx.save();
  ctx.fillStyle = design.background;
  ctx.fillRect(0, 0, w, h);
  if (pics.backdrop) {
    const img = pics.backdrop;
    const scale = Math.max(w / img.width, h / img.height) * zoom;
    const iw = img.width * scale;
    const ih = img.height * scale;
    ctx.drawImage(img, (w - iw) / 2, (h - ih) / 2, iw, ih);
    ctx.fillStyle = "rgba(0,0,0,0.5)";
    ctx.fillRect(0, 0, w, h);
  } else {
    // A soft glow in the accent colour, drifting slowly.
    const gx = w * (0.3 + 0.4 * (t / d));
    const glow = ctx.createRadialGradient(gx, h * 0.4, 0, gx, h * 0.4, w * 0.6);
    glow.addColorStop(0, `${design.accent}55`);
    glow.addColorStop(1, `${design.accent}00`);
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, w, h);
  }

  ctx.globalAlpha = alpha;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  const rise = (1 - fadeIn) * h * 0.04;
  let y = h * 0.42 + rise;

  if (pics.logo) {
    const lh = h * 0.18;
    const lw = (pics.logo.width / pics.logo.height) * lh;
    ctx.drawImage(pics.logo, (w - lw) / 2, h * 0.12 + rise, lw, lh);
    y = h * 0.5 + rise;
  }

  if (design.template === "qr") {
    const size = h * 0.42;
    const x = w * 0.62;
    if (pics.qr) {
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(x - size * 0.06, h * 0.29 - size * 0.06, size * 1.12, size * 1.12);
      ctx.drawImage(pics.qr, x, h * 0.29, size, size);
    }
    ctx.textAlign = "left";
    ctx.fillStyle = design.textColour;
    const hs = fitText(ctx, design.headline, w * 0.48, h * 0.08, 750);
    ctx.fillText(design.headline, w * 0.08, h * 0.44 + rise);
    ctx.fillStyle = design.accent;
    fitText(ctx, design.subtext, w * 0.48, h * 0.045, 500);
    ctx.fillText(design.subtext, w * 0.08, h * 0.44 + hs * 0.9 + rise);
    ctx.restore();
    return;
  }

  if (design.template === "coming_soon") {
    ctx.fillStyle = design.accent;
    fitText(ctx, "COMING SOON", w * 0.8, h * 0.05, 700);
    ctx.fillText("COMING SOON", w / 2, y - h * 0.12);
  }

  ctx.fillStyle = design.textColour;
  const size = fitText(ctx, design.headline, w * 0.84, design.template === "announcement" ? h * 0.1 : h * 0.12, 800);
  ctx.fillText(design.headline, w / 2, y);

  // An accent line that grows under the headline.
  const line = w * 0.18 * ease((t - 0.3) / 0.8);
  ctx.fillStyle = design.accent;
  ctx.fillRect(w / 2 - line / 2, y + size * 0.7, line, Math.max(3, h * 0.006));

  if (design.subtext) {
    ctx.fillStyle = design.textColour;
    ctx.globalAlpha = alpha * 0.85;
    fitText(ctx, design.subtext, w * 0.8, h * 0.05, 500);
    ctx.fillText(design.subtext, w / 2, y + size * 0.7 + h * 0.08);
  }
  ctx.restore();
}

/** Loads a local picture the person picked, for drawing. */
export function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("That picture couldn't be read."));
    img.src = src;
  });
}
