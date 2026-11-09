// First-run guide: connect a server, add videos, choose when, play a test.
// Every step can be skipped; Home keeps a checklist of what's left.
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Check, Upload } from "lucide-react";
import { usePrerolls } from "../../lib/queries";
import { useServerSummary, SERVER_TYPES } from "../../lib/servers";
import { SERVER_NAMES, type ServerType } from "../../lib/capabilities";
import { plural } from "../../lib/format";
import { Logo } from "../../components/Layout";
import { Button, ButtonLink } from "../../components/Button";
import { Notice } from "../../components/Notice";
import { TestPlay } from "../../components/TestPlay";
import { ConnectFlow } from "../servers/ConnectPage";
import { UploadDialog } from "../videos/UploadDialog";
import ScheduleWizard from "../schedules/ScheduleWizard";
import { NexrollImport } from "../settings/nexroll/NexrollImport";
import { ReplacesNexroll } from "../settings/nexroll/NexrollSection";

const STEPS = ["From NeXroll?", "Connect", "Add videos", "Choose when", "Play a test"];

function NexrollStep({ onNext }: { onNext: () => void }) {
  const [importing, setImporting] = useState(false);
  return (
    <div className="stack">
      <p>Used NeXroll before? Your collections, intro videos, schedules and media servers can come with you. This step is optional.</p>
      <ReplacesNexroll />
      {importing ? (
        <NexrollImport />
      ) : (
        <div className="form-actions">
          <Button variant="primary" onClick={() => setImporting(true)}>
            Bring my NeXroll setup over
          </Button>
          <Button onClick={onNext}>I'm new to this</Button>
        </div>
      )}
      {importing && (
        <div className="form-actions">
          <Button onClick={onNext}>Next: check your media servers</Button>
        </div>
      )}
    </div>
  );
}

function ConnectStep({ onNext }: { onNext: () => void }) {
  const { connected } = useServerSummary();
  const [type, setType] = useState<ServerType | null>(null);
  if (type) return <ConnectFlow type={type} onDone={onNext} />;
  return (
    <div className="stack">
      <p>Which media server do you use? You can add more later.</p>
      <div className="choice-grid">
        {SERVER_TYPES.map((t) => (
          <Button key={t} onClick={() => setType(t)} variant={connected.includes(t) ? "primary" : "secondary"}>
            {connected.includes(t) && <Check size={18} aria-hidden="true" />}
            {SERVER_NAMES[t]}
          </Button>
        ))}
      </div>
      {connected.length > 0 && (
        <Notice tone="success">
          {connected.map((t) => SERVER_NAMES[t]).join(" and ")} {connected.length === 1 ? "is" : "are"} already connected.{" "}
          <button type="button" className="btn-link" onClick={onNext}>Next step</button>
        </Notice>
      )}
    </div>
  );
}

function VideosStep({ onNext }: { onNext: () => void }) {
  const prerolls = usePrerolls();
  const [open, setOpen] = useState(false);
  const count = prerolls.data?.length ?? 0;
  return (
    <div className="stack">
      <p>Add the short videos that play before your movies. MP4 files work everywhere.</p>
      <div className="form-actions">
        <Button variant="primary" icon={<Upload size={18} aria-hidden="true" />} onClick={() => setOpen(true)}>
          Add videos
        </Button>
        <ButtonLink to="/videos/community">Get free ones from Community</ButtonLink>
      </div>
      {count > 0 && (
        <Notice tone="success">
          You have {plural(count, "intro video")}. <button type="button" className="btn-link" onClick={onNext}>Next step</button>
        </Notice>
      )}
      <UploadDialog open={open} onOpenChange={setOpen} onUploaded={() => undefined} />
    </div>
  );
}

export default function OnboardingPage() {
  const navigate = useNavigate();
  const { connected } = useServerSummary();
  const [step, setStep] = useState(0);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), [step]);
  const next = () => setStep((s) => Math.min(s + 1, STEPS.length - 1));

  return (
    <div className="auth-screen onboarding">
      <div className="wizard-card stack">
        <div className="row-between">
          <div className="brand">
            <Logo size={36} />
            Prerolls Max
          </div>
          <Button variant="ghost" onClick={() => navigate("/")}>
            Skip setup for now
          </Button>
        </div>
        <ol className="steps" aria-label="Setup steps">
          {STEPS.map((label, i) => (
            <li key={label} className={`step-pill ${i < step ? "done" : ""}`} aria-current={i === step ? "step" : undefined}>
              {i < step ? <Check size={14} aria-hidden="true" /> : <span aria-hidden="true">{i + 1}</span>}
              {label}
            </li>
          ))}
        </ol>
        <section className="card stack" aria-labelledby="ob-title">
          <h1 id="ob-title" ref={heading} tabIndex={-1}>
            {["Coming from NeXroll?", "Connect your media server", "Add intro videos", "Choose when they play", "Play a test"][step]}
          </h1>
          {step === 0 && <NexrollStep onNext={next} />}
          {step === 1 && <ConnectStep onNext={next} />}
          {step === 2 && <VideosStep onNext={next} />}
          {step === 3 && <ScheduleWizard embedded onSaved={next} />}
          {step === 4 && <TestPlay servers={connected} onDone={() => navigate("/")} />}
        </section>
        <div className="form-actions">
          {step > 0 && <Button onClick={() => setStep((s) => s - 1)}>Back</Button>}
          {step < STEPS.length - 1 && (
            <Button variant="ghost" onClick={next}>
              Skip this step
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
