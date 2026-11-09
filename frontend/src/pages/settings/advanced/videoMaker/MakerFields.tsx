// Colours, pictures and music for the video maker.
import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "../../../../lib/api";
import { Select } from "../../../../components/Select";
import { Button } from "../../../../components/Button";
import { ErrorNotice, Notice } from "../../../../components/Notice";
import { loadImage, type Design, type Pictures as Pics } from "./draw";

const hex = (v: string) => `#${v.replace(/^0x/i, "").replace(/^#/, "").padStart(6, "0").slice(0, 6)}`;

export function ColourFields({ design, onChange, themes }: { design: Design; onChange: (d: Design) => void; themes: Record<string, { label: string; bg: string; primary: string; accent: string }> }) {
  const [theme, setTheme] = useState("");
  const options = Object.entries(themes).map(([id, t]) => ({ value: id, label: t.label }));
  return (
    <fieldset className="plain-fieldset stack-sm">
      <legend className="field-label">Colours</legend>
      {options.length > 0 && (
        <div className="toolbar-select">
          <Select
            label={<span className="visually-hidden">Colour set</span>}
            value={theme}
            placeholder="Pick a ready-made colour set…"
            options={options}
            onChange={(id) => {
              setTheme(id);
              const t = themes[id];
              if (t) onChange({ ...design, background: hex(t.bg), accent: hex(t.primary), textColour: "#ffffff" });
            }}
          />
        </div>
      )}
      <div className="color-row">
        {(
          [
            ["background", "Background"],
            ["textColour", "Text"],
            ["accent", "Accent"],
          ] as const
        ).map(([key, label]) => (
          <label key={key} className="color-field">
            <span className="small">{label}</span>
            <input type="color" value={design[key]} onChange={(e) => onChange({ ...design, [key]: e.target.value })} />
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function PictureInput({ label, help, onPick, onClear, has }: { label: string; help: string; onPick: (img: HTMLImageElement) => void; onClear: () => void; has: boolean }) {
  const ref = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string>();
  return (
    <div className="stack-sm">
      <span className="field-label">{label}</span>
      <span className="field-help">{help}</span>
      <div className="row">
        <Button size="sm" onClick={() => ref.current?.click()}>
          {has ? "Pick another" : "Pick a picture"}
        </Button>
        {has && (
          <Button size="sm" variant="ghost" onClick={onClear}>
            Remove
          </Button>
        )}
      </div>
      <input
        ref={ref}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        className="visually-hidden"
        aria-label={label}
        tabIndex={-1}
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (!file) return;
          if (!/^image\/(png|jpeg|webp)$/.test(file.type)) {
            setError("Pick a PNG, JPEG or WebP picture.");
            return;
          }
          if (file.size > 15 * 1024 * 1024) {
            setError("That picture is too big. Keep it under 15 MB.");
            return;
          }
          setError(undefined);
          loadImage(URL.createObjectURL(file)).then(onPick, () => setError("That picture couldn't be read."));
        }}
      />
      {error && <p className="field-error">{error}</p>}
    </div>
  );
}

export function Pictures({ pics, onChange }: { pics: Pics; onChange: (p: Pics) => void }) {
  return (
    <div className="form-grid">
      <PictureInput label="Logo" help="Shown above the text. A PNG with a see-through background looks best." has={Boolean(pics.logo)} onPick={(logo) => onChange({ ...pics, logo })} onClear={() => onChange({ ...pics, logo: null })} />
      <PictureInput label="Picture behind" help="Fills the screen, darkened so the text stays readable." has={Boolean(pics.backdrop)} onPick={(backdrop) => onChange({ ...pics, backdrop })} onClear={() => onChange({ ...pics, backdrop: null })} />
    </div>
  );
}

export function MusicUpload({ onUploaded }: { onUploaded: () => void }) {
  const ref = useRef<HTMLInputElement>(null);
  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return api.post<{ filename?: string }>("/nexup/preroll/upload-audio", form, { timeoutMs: 120_000 });
    },
    onSuccess: onUploaded,
  });
  return (
    <div className="stack-sm">
      <div>
        <Button size="sm" loading={upload.isPending} onClick={() => ref.current?.click()}>
          Upload your music
        </Button>
      </div>
      <input
        ref={ref}
        type="file"
        accept="audio/*,.mp3,.m4a,.aac,.wav,.flac,.ogg,.opus"
        className="visually-hidden"
        aria-label="Music file"
        tabIndex={-1}
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (file) upload.mutate(file);
        }}
      />
      {upload.isSuccess && <Notice tone="success">Uploaded {upload.data?.filename ?? "your music"}. It plays under the intro and fades out at the end.</Notice>}
      {upload.isError && <ErrorNotice error={upload.error} />}
    </div>
  );
}
