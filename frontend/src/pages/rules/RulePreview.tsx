// "Try it": describe a title and see which rule would match and what plays.
// Nothing is recorded and nothing changes (POST /api/rules/preview).
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, Circle, FlaskConical } from "lucide-react";
import { api } from "../../lib/api";
import { useRatings, type PreviewItem, type PreviewResult } from "../../lib/rules";
import { MESSAGES, checkWhole, splitList } from "../../lib/validateSmart";
import { Button } from "../../components/Button";
import { TextField, applyServerFields } from "../../components/Field";
import { ErrorNotice } from "../../components/Notice";

const schema = z
  .object({
    item_type: z.enum(["Movie", "Episode"]),
    item_name: z.string().max(300, "Keep the title to 300 characters or fewer."),
    genres: z.string(),
    official_rating: z.string().max(40, "That rating is too long."),
    year: z.string(),
    library_name: z.string().max(200),
    user_name: z.string().max(200),
    first_in_session: z.boolean(),
  })
  .superRefine((v, ctx) => {
    if (v.year.trim() && !checkWhole(v.year, 1880, 2200, MESSAGES.year).ok) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["year"], message: MESSAGES.year });
    }
  });
type Values = z.infer<typeof schema>;

function toItem(v: Values): PreviewItem {
  return {
    item_type: v.item_type,
    item_name: v.item_name.trim(),
    genres: splitList(v.genres),
    tags: [],
    official_rating: v.official_rating.trim(),
    year: v.year.trim() ? Number(v.year) : null,
    library_name: v.library_name.trim(),
    user_name: v.user_name.trim(),
    first_in_session: v.item_type === "Episode" ? v.first_in_session : null,
  };
}

function Result({ data }: { data: PreviewResult }) {
  const list = data.order === "in_order" ? data.would_play : data.pool;
  return (
    <div className="card preview-card stack-sm" aria-live="polite">
      <p>{data.explanation}</p>
      {list.length > 0 && (
        <p className="small">
          {data.order === "in_order" ? "Plays in this order: " : `Picks ${data.count} from: `}
          {list.map((p) => p.name).join(", ")}
        </p>
      )}
      {data.fallback && <p className="small">{data.fallback}</p>}
      {data.checks.length > 0 && (
        <details className="details-toggle">
          <summary>Why each rule did or didn't match</summary>
          <ul className="plain-list check-steps">
            {data.checks.map((c) => (
              <li key={c.rule_id} className="check-step">
                {c.matched ? <CheckCircle2 size={20} className="status-ok" aria-hidden="true" /> : <Circle size={20} className="muted" aria-hidden="true" />}
                <span>
                  <strong>{c.name}</strong>
                  <span className="visually-hidden">{c.matched ? ": matches" : ": doesn't match"}</span>
                  <span className="muted small"> {c.why}</span>
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

export function RulePreview() {
  const ratings = useRatings();
  const { register, handleSubmit, watch, setError, formState: { errors } } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { item_type: "Movie", item_name: "", genres: "", official_rating: "", year: "", library_name: "", user_name: "", first_in_session: true },
  });
  const run = useMutation({
    mutationFn: (v: Values) => api.post<PreviewResult>("/api/rules/preview", { item: toItem(v) }),
    onError: (error) => applyServerFields(error, setError, ["item_name", "genres", "official_rating", "year", "library_name", "user_name"]),
  });
  // An answer is for the title that was asked about: once the details change
  // (or can't be checked, like a year of "19x4"), it goes.
  const { reset: clearAnswer, data: answer } = run;
  useEffect(() => {
    const sub = watch(() => {
      if (answer) clearAnswer();
    });
    return () => sub.unsubscribe();
  }, [watch, answer, clearAnswer]);
  const isEpisode = watch("item_type") === "Episode";
  const allRatings = [...new Set((ratings.data?.families ?? []).flatMap((f) => f.ratings.map((r) => r.value)))];

  return (
    <section className="card section" aria-labelledby="try-title">
      <h2 id="try-title" className="row">
        <FlaskConical size={22} aria-hidden="true" /> Try it
      </h2>
      <p className="muted">Describe a title and see which rule would pick its intros. Nothing plays and nothing changes.</p>
      <form className="stack" onSubmit={handleSubmit((v) => run.mutate(v), () => run.reset())} noValidate>
        <fieldset className="plain-fieldset">
          <legend className="field-label">What's starting</legend>
          <div className="row">
            <label className="checkbox">
              <input type="radio" value="Movie" {...register("item_type")} /> A movie
            </label>
            <label className="checkbox">
              <input type="radio" value="Episode" {...register("item_type")} /> A TV episode
            </label>
          </div>
        </fieldset>
        <div className="form-grid">
          <TextField label="Title" optional placeholder="The Lion King" error={errors.item_name?.message} {...register("item_name")} />
          <TextField label="Genres" optional help="Separate several with commas." placeholder="Animation, Family" error={errors.genres?.message} {...register("genres")} />
          <TextField label="Age rating" optional list="rating-values" placeholder="PG" error={errors.official_rating?.message} {...register("official_rating")} />
          <TextField label="Year" optional inputMode="numeric" placeholder="1994" error={errors.year?.message} {...register("year")} />
          <TextField label="Library" optional placeholder="Movies" error={errors.library_name?.message} {...register("library_name")} />
          <TextField label="Who's watching" optional placeholder="Their user name" error={errors.user_name?.message} {...register("user_name")} />
        </div>
        <datalist id="rating-values">
          {allRatings.map((r) => (
            <option key={r} value={r} />
          ))}
        </datalist>
        {isEpisode && (
          <label className="checkbox">
            <input type="checkbox" {...register("first_in_session")} /> It's the first episode they start after a break
          </label>
        )}
        <div>
          <Button type="submit" loading={run.isPending}>
            Show what would play
          </Button>
        </div>
      </form>
      {run.isError && !Object.keys(errors).length && <ErrorNotice error={run.error} />}
      {run.data && <Result data={run.data} />}
    </section>
  );
}
