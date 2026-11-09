// "My intro isn't playing": pick server, device and situation; live checks
// of this install plus the advice for that device.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2, XCircle, AlertTriangle } from "lucide-react";
import { api } from "../../lib/api";
import { useActiveScheduleIds, useFiller, usePrerolls } from "../../lib/queries";
import { useServerSummary, SERVER_TYPES } from "../../lib/servers";
import { SERVER_NAMES, type ServerType } from "../../lib/capabilities";
import { useMediaServers, type MediaServer, type TestStep } from "../../lib/mediaServers";
import { ButtonLink } from "../../components/Button";
import { FieldShell } from "../../components/Field";
import { Loading, Notice } from "../../components/Notice";
import { PageHeader } from "../../components/HelpPanel";
import { DEVICES, situationAdvice } from "./troubleshoot";

type Check = { ok: boolean | "warn"; text: string; fix?: { to: string; label: string } };

function LiveChecks({ server, picked }: { server: ServerType; picked?: MediaServer }) {
  const { all } = useServerSummary();
  // One server from the list: its own connection test (the same as on Media Servers).
  const test = useQuery({
    queryKey: ["server-test", picked?.id],
    enabled: Boolean(picked),
    retry: false,
    queryFn: async () => (await api.post<{ steps: TestStep[] }>(`/api/servers/${picked?.id}/test`, {}, { timeoutMs: 60_000 })).steps,
  });
  const prerolls = usePrerolls();
  const active = useActiveScheduleIds();
  const filler = useFiller();
  const plugin = useQuery({
    queryKey: ["plugin-detect", server],
    enabled: !picked && server !== "plex" && Boolean(all[server].data?.connected),
    queryFn: () => api.get<{ detected?: boolean }>(`/${server}/plugin/detect`),
  });
  // Ask Plex itself whether the files Prerolls Max gave it are there (live, not advice).
  const plexFiles = useQuery({
    queryKey: ["plex-preroll-check"],
    enabled: !picked && server === "plex" && Boolean(all.plex.data?.connected),
    retry: false,
    queryFn: () =>
      api.get<{ reachable?: boolean; action?: string; value?: string }>("/plex/preroll-check", undefined, { timeoutMs: 40_000 }),
  });
  const status = all[server];
  if (status.isLoading || prerolls.isLoading || active.isLoading || filler.isLoading || (picked && test.isLoading)) {
    return <Loading label="Checking your setup…" />;
  }

  const name = picked?.name ?? SERVER_NAMES[server];
  const own: Check[] = picked
    ? (test.data ?? [])
        .filter((step) => step.state !== "skipped")
        .map((step) => ({
          ok: step.state === "ok" ? true : step.state === "warn" ? "warn" : false,
          text: step.detail ? `${step.title}: ${step.detail}` : `${step.title}.`,
          fix: step.link ?? undefined,
        }))
    : [];
  const checks: Check[] = [
    ...(picked
      ? own
      : [
          status.data?.connected
            ? { ok: true, text: `Prerolls Max is connected to ${name}.` }
            : { ok: false, text: `Prerolls Max isn't connected to ${name}.`, fix: { to: `/servers/${server}`, label: `Connect ${name}` } },
        ] as Check[]),
    (prerolls.data?.length ?? 0) > 0
      ? { ok: true, text: `You have ${prerolls.data?.length} intro videos.` }
      : { ok: false, text: "You don't have any intro videos yet.", fix: { to: "/videos", label: "Add videos" } },
    (active.data?.length ?? 0) > 0 || filler.data?.enabled
      ? { ok: true, text: "Something is set to play right now." }
      : { ok: false, text: "No schedule is on right now, and default intros are off.", fix: { to: "/schedules", label: "Set default intros" } },
  ];
  if (!picked && server !== "plex" && status.data?.connected) {
    checks.push(
      plugin.isLoading
        ? { ok: "warn", text: "Checking for the plugin…" }
        : plugin.data?.detected
          ? { ok: true, text: `The Prerolls Max plugin is installed in ${name}.` }
          : { ok: false, text: `The Prerolls Max plugin isn't installed in ${name}.`, fix: { to: `/help/connect-${server}`, label: "How to install it" } },
    );
  }
  if (!picked && server === "plex" && status.data?.connected) {
    const seen = plexFiles.data;
    checks.push(
      plexFiles.isLoading
        ? { ok: "warn", text: "Asking Plex whether it can see your intro files…" }
        : seen?.action === "ok" && seen.value
          ? { ok: true, text: "Plex can see the intro files Prerolls Max gave it." }
          : seen && !seen.value
            ? { ok: "warn", text: "Nothing has been sent to Plex yet, so there's nothing to check.", fix: { to: "/schedules", label: "Choose when intros play" } }
            : { ok: false, text: "Plex can't find the intro files where Prerolls Max says they are. This is common when either one runs in Docker.", fix: { to: "/settings/advanced/folder-mapping", label: "Set up folder mapping" } },
    );
  }
  return (
    <ul className="check-steps">
      {checks.map((c) => (
        <li key={c.text} className="check-step">
          {c.ok === true ? (
            <CheckCircle2 size={22} className="status-ok" aria-label="OK" />
          ) : c.ok === "warn" ? (
            <AlertTriangle size={22} className="status-warn" aria-label="Check" />
          ) : (
            <XCircle size={22} className="status-bad" aria-label="Problem" />
          )}
          <div className="grow">
            {c.text} {c.fix && <Link to={c.fix.to}>{c.fix.label}</Link>}
          </div>
        </li>
      ))}
    </ul>
  );
}

function RadioGroup<T extends string>({ label, name, value, onChange, options }: { label: string; name: string; value: T | ""; onChange: (v: T) => void; options: { value: T; label: string }[] }) {
  return (
    <FieldShell label={label} group>
      {() => (
        <div className="choice-grid">
          {options.map((o) => (
            <label key={o.value} className="choice">
              <input type="radio" name={name} value={o.value} checked={value === o.value} onChange={() => onChange(o.value)} />
              <span className="choice-title">{o.label}</span>
            </label>
          ))}
        </div>
      )}
    </FieldShell>
  );
}

export default function TroubleshooterPage() {
  const { connected } = useServerSummary();
  const list = useMediaServers();
  const known = (list.data ?? []).filter((s) => s.enabled);
  const [choice, setChoice] = useState("");
  const picked = known.find((s) => `id:${s.id}` === choice);
  const server: ServerType | "" = picked ? picked.type : (choice as ServerType | "");
  const [device, setDevice] = useState("");
  const [kind, setKind] = useState<"movie" | "episode" | "">("");
  const [resumed, setResumed] = useState<"yes" | "no" | "">("");

  useEffect(() => {
    if (choice) return;
    if (known.length === 1 && known[0]) setChoice(`id:${known[0].id}`);
    else if (!known.length && connected.length === 1 && connected[0]) setChoice(connected[0]);
  }, [connected, known, choice]);
  const serverOptions = known.length
    ? known.map((s) => ({ value: `id:${s.id}`, label: known.filter((k) => k.type === s.type).length > 1 || s.name !== s.type_label ? `${s.name} (${s.type_label})` : s.name }))
    : SERVER_TYPES.map((t) => ({ value: t as string, label: SERVER_NAMES[t] }));

  const chosen = server ? DEVICES[server].find((d) => d.id === device) : undefined;
  const advice = server && kind && resumed ? situationAdvice(server, kind, resumed === "yes") : [];

  return (
    <>
      <ButtonLink to="/help" variant="ghost" size="sm" icon={<ArrowLeft size={16} aria-hidden="true" />}>
        All help
      </ButtonLink>
      <PageHeader title="My intro isn't playing" description="Answer three questions. We'll check your setup as you go." />
      <div className="stack">
        <section className="card stack">
          <RadioGroup
            label="1. Which media server?"
            name="server"
            value={choice}
            onChange={(v) => {
              setChoice(v);
              setDevice("");
            }}
            options={serverOptions}
          />
          {server && <LiveChecks key={choice} server={server} picked={picked} />}
        </section>
        {server && (
          <section className="card stack">
            <RadioGroup label="2. What are you watching on?" name="device" value={device} onChange={setDevice} options={DEVICES[server].map((d) => ({ value: d.id, label: d.label }))} />
            {chosen && (
              <Notice tone={chosen.works === "yes" ? "success" : chosen.works === "no" ? "error" : "warning"} title={chosen.works === "yes" ? "Intros play on this device" : chosen.works === "no" ? "This app can't play intros" : "This needs one setting changed"}>
                {chosen.advice && <p>{chosen.advice}</p>}
              </Notice>
            )}
          </section>
        )}
        {server && device && (
          <section className="card stack">
            <RadioGroup label="3. What did you play?" name="kind" value={kind} onChange={setKind} options={[{ value: "movie", label: "A movie" }, { value: "episode", label: "A TV episode" }]} />
            <RadioGroup label="Did you start it from the beginning?" name="resumed" value={resumed} onChange={setResumed} options={[{ value: "no", label: "Yes, from the start" }, { value: "yes", label: "No, I resumed it" }]} />
            {advice.length > 0 && (
              <Notice tone="info" title="Things to check">
                <ul>
                  {advice.map((a) => (
                    <li key={a}>{a}</li>
                  ))}
                </ul>
              </Notice>
            )}
            {advice.length > 0 && (
              <p className="muted">
                Still stuck? <Link to="/help/report">Report a problem</Link> and say which server and device you use.
              </p>
            )}
          </section>
        )}
      </div>
    </>
  );
}
