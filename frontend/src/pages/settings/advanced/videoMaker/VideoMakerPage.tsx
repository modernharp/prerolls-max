// Advanced > Video maker: a short intro from text, colours, a logo, a
// picture behind it and music. Saved straight into the library.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../../../lib/api";
import { keys } from "../../../../lib/queries";
import { cleanName } from "../../../../lib/validate";
import { TextField } from "../../../../components/Field";
import { Select } from "../../../../components/Select";
import { Button } from "../../../../components/Button";
import { ErrorNotice, Loading, Notice, ProgressBar } from "../../../../components/Notice";
import { useSaveTrailerSettings, useTrailerSettings } from "../trailers/useTrailers";
import { loadImage, type Design, type Pictures, type TemplateId } from "./draw";
import { Preview } from "./Preview";
import { renderIntro } from "./render";
import { Pictures as PictureFields, ColourFields, MusicUpload } from "./MakerFields";

const TEMPLATES: { id: TemplateId; title: string; desc: string; headline: string; subtext: string }[] = [
  { id: "welcome", title: "Welcome", desc: "Your server's name, big and simple.", headline: "Welcome to our cinema", subtext: "Sit back and enjoy the show" },
  { id: "coming_soon", title: "Coming soon", desc: "A teaser before the feature.", headline: "Our Home Cinema", subtext: "New movies every week" },
  { id: "announcement", title: "Announcement", desc: "Any message, like house rules.", headline: "Please silence your phones", subtext: "The movie is about to start" },
  { id: "qr", title: "QR code", desc: "A code people can scan, with a caption.", headline: "Request a movie", subtext: "Scan the code with your phone" },
];

export function VideoMakerPage() {
  const settings = useTrailerSettings();
  const saveSettings = useSaveTrailerSettings();
  const queryClient = useQueryClient();
  const templates = useQuery({
    queryKey: ["maker-templates"],
    queryFn: () => api.get<{ ffmpeg_available: boolean; color_themes: Record<string, { label: string; bg: string; primary: string; accent: string }> }>("/nexup/preroll/templates"),
  });
  const [design, setDesign] = useState<Design>({
    template: "welcome",
    headline: TEMPLATES[0]!.headline,
    subtext: TEMPLATES[0]!.subtext,
    qrText: "",
    background: "#141428",
    textColour: "#ffffff",
    accent: "#00d4ff",
    duration: 6,
  });
  const [pics, setPics] = useState<Pictures>({});
  const [name, setName] = useState("Welcome card");
  const [audio, setAudio] = useState<"none" | "default" | "custom">("none");
  const [musicReady, setMusicReady] = useState(false);
  const [errors, setErrors] = useState<Record<string, string | undefined>>({});
  const [progress, setProgress] = useState<{ percent: number; message: string } | null>(null);

  // The QR code is drawn by the server, so it scans the same in the preview and the video.
  useEffect(() => {
    if (design.template !== "qr" || !/^\S{3,}$/.test(design.qrText.trim())) {
      setPics((p) => ({ ...p, qr: null }));
      return;
    }
    const timer = window.setTimeout(() => {
      loadImage(`/nexup/preroll/qr?data=${encodeURIComponent(design.qrText.trim())}&size=620`)
        .then((qr) => setPics((p) => ({ ...p, qr })))
        .catch(() => setPics((p) => ({ ...p, qr: null })));
    }, 400);
    return () => window.clearTimeout(timer);
  }, [design.template, design.qrText]);

  const render = useMutation({
    mutationFn: (clean: string) => renderIntro(design, pics, { name: clean, audioMode: audio, onProgress: (percent, message) => setProgress({ percent, message }) }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.prerolls }),
    onError: () => setProgress(null),
  });

  const pickTemplate = (id: TemplateId) => {
    const t = TEMPLATES.find((x) => x.id === id)!;
    setDesign((d) => ({ ...d, template: id, headline: t.headline, subtext: t.subtext }));
    setName(`${t.title} card`);
  };

  const submit = () => {
    const next: Record<string, string | undefined> = {};
    const head = cleanName(design.headline, { what: "headline", maxLen: 80 });
    if (!head.ok) next.headline = head.message;
    if (design.subtext.length > 120) next.subtext = "Keep this line to 120 characters or fewer.";
    if (design.template === "qr" && !design.qrText.trim()) next.qrText = "Enter the link or text the code should open.";
    else if (design.qrText.length > 2000) next.qrText = "That's too long for a QR code. Keep it under 2000 characters.";
    if (!Number.isInteger(design.duration) || design.duration < 3 || design.duration > 30) next.duration = "Use a whole number from 3 to 30.";
    if (audio === "custom" && !musicReady) next.music = "Upload your music first, or pick another option.";
    const label = cleanName(name, { what: "name", maxLen: 60 });
    if (!label.ok) next.name = label.message;
    setErrors(next);
    if (Object.values(next).some(Boolean) || !label.ok) return;
    setProgress({ percent: 0, message: "Getting ready…" });
    render.mutate(label.value);
  };

  if (settings.isLoading || templates.isLoading) return <Loading />;
  if (settings.isError) return <ErrorNotice error={settings.error} onRetry={() => settings.refetch()} />;
  const storage = settings.data?.storage_path;

  return (
    <div className="stack">
      {!storage && (
        <Notice tone="info" title="First, a folder for made videos">
          <p>Prerolls Max keeps videos it makes in the same folder as movie trailers. Suggested: {settings.data?.recommended_storage_path}</p>
          {saveSettings.isError && <ErrorNotice error={saveSettings.error} />}
          <Button size="sm" variant="primary" loading={saveSettings.isPending} onClick={() => saveSettings.mutate({ storage_path: settings.data?.recommended_storage_path })}>
            Use the suggested folder
          </Button>
        </Notice>
      )}
      {templates.data && !templates.data.ffmpeg_available && (
        <Notice tone="warning">FFmpeg isn't installed, so videos can't be made yet. See System and updates.</Notice>
      )}
      <div className="maker-layout">
        <div className="stack">
          <fieldset className="plain-fieldset">
            <legend className="field-label">Start from</legend>
            <div className="template-grid">
              {TEMPLATES.map((t) => (
                <label key={t.id} className="choice">
                  <input type="radio" name="template" checked={design.template === t.id} onChange={() => pickTemplate(t.id)} />
                  <span>
                    <span className="choice-title">{t.title}</span>
                    <span className="choice-desc">{t.desc}</span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
          <TextField label={design.template === "coming_soon" ? "Your server's name" : "Headline"} value={design.headline} error={errors.headline} onChange={(e) => setDesign({ ...design, headline: e.target.value })} />
          <TextField label={design.template === "qr" ? "Caption" : "Second line"} optional={design.template !== "qr"} value={design.subtext} error={errors.subtext} onChange={(e) => setDesign({ ...design, subtext: e.target.value })} />
          {design.template === "qr" && (
            <TextField label="Link the code opens" placeholder="https://requests.example.com" inputMode="url" value={design.qrText} error={errors.qrText} onChange={(e) => setDesign({ ...design, qrText: e.target.value })} />
          )}
          <ColourFields design={design} onChange={setDesign} themes={templates.data?.color_themes ?? {}} />
          <PictureFields pics={pics} onChange={setPics} />
          <div className="form-grid">
            <TextField label="Length (seconds)" type="number" min={3} max={30} value={design.duration} error={errors.duration} onChange={(e) => setDesign({ ...design, duration: Number(e.target.value) })} />
            <Select
              label="Music"
              value={audio}
              onChange={(v) => setAudio(v as typeof audio)}
              options={[
                { value: "none", label: "No music" },
                { value: "default", label: "The built-in fanfare" },
                { value: "custom", label: "Your own music" },
              ]}
            />
          </div>
          {audio === "custom" && <MusicUpload onUploaded={() => setMusicReady(true)} />}
          {errors.music && <p className="field-error">{errors.music}</p>}
          <TextField label="Save it as" help="The name it gets in your library." value={name} error={errors.name} onChange={(e) => setName(e.target.value)} />
          {render.isError && <ErrorNotice error={render.error} />}
          {progress && render.isPending && (
            <div className="stack-sm" aria-live="polite">
              <ProgressBar value={progress.percent} label="Making the video" />
              <p className="muted small">{progress.message}</p>
            </div>
          )}
          {render.isSuccess && (
            <Notice tone="success" title={`Made "${name}"`}>
              It's in your library. <Link to="/videos">See it in Your videos</Link>, or add it to a schedule.
            </Notice>
          )}
          <div>
            <Button variant="primary" onClick={submit} loading={render.isPending} disabled={!storage}>
              Make the video
            </Button>
          </div>
        </div>
        <div className="maker-preview stack-sm">
          <Preview design={design} pics={pics} />
          <p className="muted small">The preview plays on a loop. The video plays once, {design.duration} seconds long.</p>
        </div>
      </div>
    </div>
  );
}
