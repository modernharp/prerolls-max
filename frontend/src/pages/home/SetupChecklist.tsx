// Setup checklist on Home, shown until every step is done.
import { useState } from "react";
import { CheckCircle2, Circle } from "lucide-react";
import { usePrerolls, useSchedules } from "../../lib/queries";
import { usePrefs } from "../../lib/prefs";
import { ButtonLink, Button } from "../../components/Button";
import { Modal } from "../../components/Dialog";
import { TestPlay } from "../../components/TestPlay";
import { useServerSummary } from "../../lib/servers";

export function SetupChecklist() {
  const servers = useServerSummary();
  const prerolls = usePrerolls();
  const schedules = useSchedules();
  const { testPlayed } = usePrefs();
  const [testing, setTesting] = useState(false);

  if (servers.loading || prerolls.isLoading || schedules.isLoading) return null;

  const steps = [
    { done: servers.connected.length > 0, title: "Connect a media server", text: "Plex, Jellyfin or Emby.", action: <ButtonLink to="/servers" size="sm">Connect</ButtonLink> },
    { done: (prerolls.data?.length ?? 0) > 0, title: "Add intro videos", text: "Upload your own or get free ones from the Community.", action: <ButtonLink to="/videos" size="sm">Add videos</ButtonLink> },
    { done: (schedules.data?.length ?? 0) > 0, title: "Choose when they play", text: "Every day, on certain dates, or on weekends.", action: <ButtonLink to="/schedules/new" size="sm">Choose</ButtonLink> },
    { done: testPlayed, title: "Play a test", text: "Play a movie and check the intro plays first.", action: <Button size="sm" onClick={() => setTesting(true)}>Start test</Button> },
  ];
  if (steps.every((s) => s.done)) return null;
  const doneCount = steps.filter((s) => s.done).length;
  const firstOpen = steps.findIndex((s) => !s.done);

  return (
    <section className="card section" aria-labelledby="checklist-title">
      <div className="row-between">
        <h2 id="checklist-title">Finish setting up</h2>
        <span className="muted small">
          {doneCount} of {steps.length} done
        </span>
      </div>
      <ol className="checklist">
        {steps.map((s, i) => (
          <li key={s.title} className={s.done ? "done" : ""}>
            {s.done ? (
              <CheckCircle2 size={24} className="status-ok" aria-hidden="true" />
            ) : (
              <Circle size={24} className="muted" aria-hidden="true" />
            )}
            <div className="grow">
              <strong>
                {s.title}
                <span className="visually-hidden">{s.done ? " (done)" : " (to do)"}</span>
              </strong>
              <div className="muted small">{s.text}</div>
            </div>
            {!s.done && i === firstOpen && s.action}
          </li>
        ))}
      </ol>
      <Modal open={testing} onOpenChange={setTesting} title="Play a test">
        <TestPlay servers={servers.connected} onDone={() => setTesting(false)} />
      </Modal>
    </section>
  );
}
