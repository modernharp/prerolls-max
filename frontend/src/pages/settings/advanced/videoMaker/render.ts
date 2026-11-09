// Records the design in the browser and has Prerolls Max turn the recording
// into an MP4 in the library. Progress comes in two parts: recording (in
// real time, as long as the intro) and making the file on the server.
import { api } from "../../../../lib/api";
import { drawFrame, type Design, type Pictures } from "./draw";

export interface RenderOptions {
  name: string;
  audioMode: "none" | "default" | "custom";
  onProgress: (percent: number, message: string) => void;
}

const BACKEND_TEMPLATE: Record<Design["template"], string> = {
  welcome: "custom_text",
  coming_soon: "coming_soon",
  announcement: "custom_text",
  qr: "qr_share",
};

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error("The recording couldn't be read."));
    reader.readAsDataURL(blob);
  });
}

function pickMime(): string | null {
  if (typeof MediaRecorder === "undefined") return null;
  for (const type of ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"]) {
    if (MediaRecorder.isTypeSupported(type)) return type;
  }
  return null;
}

async function record(design: Design, pics: Pictures, onProgress: RenderOptions["onProgress"]): Promise<{ video?: string; image?: string; mime?: string }> {
  const canvas = document.createElement("canvas");
  canvas.width = 1920;
  canvas.height = 1080;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("This browser can't draw the video.");
  const mime = pickMime();
  if (!mime || typeof canvas.captureStream !== "function") {
    // No recorder: send one still picture; the server fades it in and out.
    drawFrame(ctx, canvas.width, canvas.height, design, pics, design.duration / 2);
    return { image: canvas.toDataURL("image/png") };
  }
  const stream = canvas.captureStream(30);
  const recorder = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 8_000_000 });
  const chunks: Blob[] = [];
  recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
  const stopped = new Promise<void>((resolve) => (recorder.onstop = () => resolve()));
  const start = performance.now();
  drawFrame(ctx, canvas.width, canvas.height, design, pics, 0);
  recorder.start(250);
  await new Promise<void>((resolve) => {
    const tick = () => {
      const t = (performance.now() - start) / 1000;
      drawFrame(ctx, canvas.width, canvas.height, design, pics, Math.min(t, design.duration));
      onProgress(Math.min(60, (t / design.duration) * 60), `Recording the animation (${Math.min(design.duration, Math.floor(t))} of ${design.duration} seconds)…`);
      if (t >= design.duration + 0.2) resolve();
      else requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
  recorder.stop();
  await stopped;
  stream.getTracks().forEach((track) => track.stop());
  return { video: await blobToDataUrl(new Blob(chunks, { type: mime })), mime };
}

export interface RenderResult {
  filename: string;
  path: string;
}

export async function renderIntro(design: Design, pics: Pictures, options: RenderOptions): Promise<RenderResult> {
  options.onProgress(2, "Getting ready…");
  const captured = await record(design, pics, options.onProgress);
  // The server doesn't report how far it got, so the bar holds here instead
  // of pretending; the words say what's happening.
  options.onProgress(70, "Recorded. Making your video… this can take a minute.");
  try {
    const result = await api.post<RenderResult>(
      "/nexup/preroll/generate-from-preview",
      {
        video_data: captured.video ?? null,
        video_mime_type: captured.mime ?? null,
        image_data: captured.image ?? null,
        duration: design.duration,
        template: BACKEND_TEMPLATE[design.template],
        theme: "custom",
        server_name: design.template === "coming_soon" ? design.headline : "",
        resolution: "1080",
        frame_rate: 30,
        quality: "balanced",
        audio_mode: options.audioMode,
        custom_headline: design.headline,
        custom_subtext: design.subtext,
        qr_data: design.template === "qr" ? design.qrText : null,
        qr_caption: design.template === "qr" ? design.subtext : null,
        name: options.name,
      },
      { timeoutMs: 5 * 60_000 },
    );
    options.onProgress(100, "Done");
    return result;
  } catch (error) {
    options.onProgress(0, "");
    throw error;
  }
}
