// The loudness line above Your videos: how many intros are too loud or too
// quiet, a button to check them, and one to even out the ones that stand out.
import { Volume2 } from "lucide-react";
import type { LoudnessOverview } from "../../../lib/media";
import { plural } from "../../../lib/format";
import { Button } from "../../../components/Button";
import { ErrorNotice } from "../../../components/Notice";
import { FeatureBadges } from "../../../components/FeatureBadges";
import { JobProgress, type useMediaJob } from "./useMediaJob";

interface Props {
  data?: LoudnessOverview;
  /** Intros switched off because a version plays instead: left out of the counts. */
  skip?: Set<number>;
  check: ReturnType<typeof useMediaJob<{ checked: number }>>;
  onEvenOut: (ids: number[]) => void;
}

export function LoudnessSummary({ data, skip, check, onEvenOut }: Props) {
  if (!data || !data.items.length) return null;
  const items = data.items.filter((i) => !skip?.has(i.preroll_id));
  const c: Partial<Record<string, number>> = {};
  for (const i of items) c[i.status] = (c[i.status] ?? 0) + 1;
  const unchecked = c.unchecked ?? 0;
  const outliers = items.filter((i) => ["loud", "quiet", "peaks"].includes(i.status)).map((i) => i.preroll_id);
  const parts = [
    c.loud && `${c.loud} too loud`,
    c.quiet && `${c.quiet} too quiet`,
    c.peaks && `${c.peaks} clipping`,
    c.ok && `${c.ok} even`,
    unchecked && `${unchecked} not checked yet`,
  ].filter(Boolean);

  return (
    <section className="card loudness-summary" aria-labelledby="loud-title">
      <div className="row-between">
        <div className="row grow">
          <Volume2 size={22} aria-hidden="true" />
          <div>
            <h2 id="loud-title" className="h4-like">Loudness</h2>
            <p className="muted small">
              {parts.length ? `${parts.join(" · ")}. ` : ""}Target {data.target_lufs} LUFS, the level films are mixed at.
            </p>
          </div>
        </div>
        <div className="form-actions">
          <Button
            size="sm"
            loading={check.running}
            onClick={() => check.start.mutate(unchecked ? { preroll_ids: items.filter((i) => i.status === "unchecked").map((i) => i.preroll_id) } : {})}
          >
            {check.running ? "Checking…" : unchecked ? `Check ${plural(unchecked, "intro")}` : "Check all again"}
          </Button>
          {outliers.length > 0 && (
            <Button size="sm" variant="primary" onClick={() => onEvenOut(outliers)}>
              Even out {outliers.length === 1 ? "the one" : `the ${outliers.length}`} that stand{outliers.length === 1 ? "s" : ""} out
            </Button>
          )}
        </div>
      </div>
      <FeatureBadges feature="loudness" />
      {check.start.isError && <ErrorNotice error={check.start.error} />}
      {check.job && !check.finished && <JobProgress job={check.job} error={check.jobError} label="Checking loudness" />}
      {check.job?.state === "done" && check.job.errors.length > 0 && <JobProgress job={check.job} label="Checking loudness" />}
    </section>
  );
}
