import { useEffect } from "react";
import { Link, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight, Monitor, Moon, Sun } from "lucide-react";
import { api } from "../../lib/api";
import { setAdvanced, setTheme, usePrefs, type Theme } from "../../lib/prefs";
import { PageHeader } from "../../components/HelpPanel";
import { SwitchRow } from "../../components/Controls";
import { TimeZoneSection } from "./TimeZoneSection";
import { AccountSection } from "./AccountSection";
import { BackupSection } from "./BackupSection";
import { PlaybackSection } from "./PlaybackSection";
import { NexrollSection } from "./nexroll/NexrollSection";
import { ADVANCED_PAGES } from "./advanced/pages";

const THEMES: { value: Theme; label: string; icon: typeof Sun }[] = [
  { value: "system", label: "Same as my device", icon: Monitor },
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
];

function Appearance() {
  const { theme } = usePrefs();
  return (
    <fieldset className="plain-fieldset">
      <legend className="field-label">Colours</legend>
      <div className="choice-grid">
        {THEMES.map(({ value, label, icon: Icon }) => (
          <label key={value} className="choice">
            <input type="radio" name="theme" value={value} checked={theme === value} onChange={() => setTheme(value)} />
            <Icon size={20} aria-hidden="true" />
            <span className="choice-title">{label}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function About() {
  const version = useQuery({ queryKey: ["version"], queryFn: () => api.get<{ api_version: string }>("/system/version") });
  return (
    <div className="stack-sm">
      <p>
        <strong>Prerolls Max</strong> {version.data ? `version ${version.data.api_version}` : ""}
      </p>
      <p>
        Prerolls Max started as a fork of{" "}
        <a href="https://github.com/JFLXCLOUD/NeXroll" target="_blank" rel="noreferrer noopener">
          NeXroll
        </a>{" "}
        2.4.0 by JFLXCLOUD. Thank you to everyone who built it. The scheduling, playlist, trailer and video maker code
        comes from their work.
      </p>
      <p>
        Community intros come from{" "}
        <a href="https://www.prerolls.me" target="_blank" rel="noreferrer noopener">Prerolls.me</a> and{" "}
        <a href="https://typicalnerds.uk" target="_blank" rel="noreferrer noopener">Prerolls.uk by Typical Nerds</a>. Each video
        is credited to the person who made it.
      </p>
      <p className="muted small">Released under the MIT licence. Copyright 2024 JFLXCLOUD (NeXroll), 2026 Prerolls Max contributors.</p>
    </div>
  );
}

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="card section settings-section" aria-labelledby={`${id}-title`}>
      <h2 id={`${id}-title`}>{title}</h2>
      {children}
    </section>
  );
}

export default function SettingsPage() {
  const { advanced } = usePrefs();
  const { hash } = useLocation();
  useEffect(() => {
    // Links like /settings#time-zone come from other pages.
    const id = hash.replace("#", "");
    if (id) document.getElementById(id)?.scrollIntoView({ block: "start" });
  }, [hash]);

  return (
    <>
      <PageHeader title="Settings" helpSlug="settings" />
      <Section id="appearance" title="Appearance">
        <Appearance />
      </Section>
      <Section id="playback" title="Playback">
        <PlaybackSection />
      </Section>
      <Section id="time-zone" title="Time zone">
        <TimeZoneSection />
      </Section>
      <Section id="account" title="Account and sign-in">
        <AccountSection />
      </Section>
      <Section id="backup" title="Backup and restore">
        <BackupSection />
      </Section>
      <Section id="nexroll" title="Moving from NeXroll">
        <NexrollSection />
      </Section>
      <Section id="advanced" title="Advanced">
        <SwitchRow
          label="Show advanced options"
          description="Playlists, movie trailers, the video maker, folder mapping, logs and more. Most people never need these."
          checked={advanced}
          onChange={setAdvanced}
        />
        {advanced && (
          <ul className="list advanced-list">
            {ADVANCED_PAGES.map((p) => (
              <li key={p.slug}>
                <Link to={`/settings/advanced/${p.slug}`} className="list-row link-row">
                  <div className="grow">
                    <strong>{p.title}</strong>
                    {!p.ready && <span className="badge badge-warning">Coming soon</span>}
                    <div className="muted small">{p.summary}</div>
                  </div>
                  <ChevronRight size={20} aria-hidden="true" />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Section>
      <Section id="about" title="About">
        <About />
      </Section>
    </>
  );
}
