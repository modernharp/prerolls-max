// The live preview: plays the design on a loop.
import { useEffect, useRef } from "react";
import { drawFrame, type Design, type Pictures } from "./draw";

export function Preview({ design, pics, paused }: { design: Design; pics: Pictures; paused?: boolean }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const latest = useRef({ design, pics });
  latest.current = { design, pics };

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return undefined;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    let frame = 0;
    const start = performance.now();
    const tick = () => {
      const { design: d, pics: p } = latest.current;
      const loop = d.duration + 0.8;
      const t = reduce || paused ? d.duration / 2 : ((performance.now() - start) / 1000) % loop;
      drawFrame(ctx, canvas.width, canvas.height, d, p, Math.min(t, d.duration));
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [paused]);

  return (
    <canvas
      ref={ref}
      className="maker-canvas"
      width={960}
      height={540}
      role="img"
      aria-label={`Preview: ${design.headline}${design.subtext ? `, ${design.subtext}` : ""}`}
    />
  );
}
