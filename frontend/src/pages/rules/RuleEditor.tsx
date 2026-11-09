// Make or change one rule: a name, "When" and "Play".
import { useEffect } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../../lib/api";
import { ruleKeys, useRules, type Rule } from "../../lib/rules";
import { checkNameFree } from "../../lib/names";
import { EMPTY_RULE, draftToRuleIn, ruleSchema, ruleToDraft, type RuleDraft } from "../../lib/validateSmart";
import { PageHeader } from "../../components/HelpPanel";
import { Button, ButtonLink } from "../../components/Button";
import { TextField, applyServerFields } from "../../components/Field";
import { SwitchRow } from "../../components/Controls";
import { ErrorNotice, Loading, Notice } from "../../components/Notice";
import { FeatureBadges } from "../../components/FeatureBadges";
import { useToast } from "../../components/Toast";
import { RuleWhenFields } from "./RuleWhenFields";
import { RulePlayFields } from "./RulePlayFields";

const STARTS: Record<string, Partial<RuleDraft>> = {
  kids: { name: "Kids", kids_safe: true },
  horror: { name: "80s horror", genres: "Horror", decades: ["1980s"], media_type: "movie", order: "in_order" },
  binge: { name: "Start of a binge", media_type: "episode", first_episode_only: true },
};

const FIELDS = Object.keys(EMPTY_RULE);

export default function RuleEditor() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const isNew = !id;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();
  const existing = useQuery({
    queryKey: ["rule", id],
    enabled: !isNew,
    queryFn: () => api.get<Rule>(`/api/rules/${id}`),
  });
  const form = useForm<RuleDraft>({
    resolver: zodResolver(ruleSchema),
    mode: "onTouched",
    defaultValues: { ...EMPTY_RULE, ...(isNew ? STARTS[params.get("start") ?? ""] : {}) },
  });
  const { register, control, handleSubmit, reset, setError, formState: { errors, isSubmitted } } = form;
  const rules = useRules();
  const start = params.get("start") ?? "";

  useEffect(() => {
    if (existing.data) reset(ruleToDraft(existing.data));
  }, [existing.data, reset]);

  // Going to another starting point (say, the Kids template from "Start from
  // scratch") on the same page starts the form again from that template.
  useEffect(() => {
    if (isNew) reset({ ...EMPTY_RULE, ...STARTS[start] });
  }, [isNew, start, reset]);

  const submit = (d: RuleDraft) => {
    const taken = checkNameFree("rule", rules.data?.rules, d.name, existing.data?.id, existing.data?.name);
    if (taken) return setError("name", { type: "taken", message: taken });
    save.mutate(d);
  };

  const save = useMutation({
    mutationFn: (d: RuleDraft) => (isNew ? api.post<Rule>("/api/rules", draftToRuleIn(d)) : api.put<Rule>(`/api/rules/${id}`, draftToRuleIn(d))),
    onSuccess: async (rule) => {
      await queryClient.invalidateQueries({ queryKey: ruleKeys.rules });
      queryClient.removeQueries({ queryKey: ["rule", id] });
      const done = isNew ? `Made the rule "${rule.name}"` : `Saved "${rule.name}"`;
      toast(
        rule.problem
          ? { tone: "info", title: `${done}, but it can't play anything yet`, description: `${rule.problem} It's skipped until that's fixed.` }
          : { tone: "success", title: done, description: rule.summary },
      );
      navigate("/schedules/rules");
    },
    onError: (error) => applyServerFields(error, setError, FIELDS, [[/year/i, "year_to"], [/collection/i, "collection_id"]]),
  });

  return (
    <>
      <ButtonLink to="/schedules/rules" variant="ghost" size="sm" icon={<ArrowLeft size={16} aria-hidden="true" />}>
        Rules
      </ButtonLink>
      <PageHeader
        title={isNew ? "New rule" : "Edit rule"}
        description="When a title like this is about to play, play these intros."
        helpSlug="rules"
      />
      <div className="row section-gap">
        <span className="muted small">Every option below works on:</span>
        <FeatureBadges feature="rule_sets" />
      </div>
      {existing.isLoading ? (
        <Loading />
      ) : existing.isError ? (
        <ErrorNotice error={existing.error} onRetry={() => existing.refetch()} />
      ) : (
        <form className="stack" onSubmit={handleSubmit(submit)} noValidate>
          <section className="card stack">
            <TextField label="Name" placeholder="For example: Kids" error={errors.name?.message} {...register("name")} />
            <Controller
              control={control}
              name="enabled"
              render={({ field }) => (
                <SwitchRow label="On" description="Turn it off to skip this rule without deleting it." checked={field.value} onChange={field.onChange} />
              )}
            />
          </section>
          <RuleWhenFields form={form} />
          <RulePlayFields form={form} />
          {existing.data?.problem && <Notice tone="warning" title="This rule can't play anything right now">{existing.data.problem}</Notice>}
          {isSubmitted && Object.keys(errors).length > 0 && (
            <Notice tone="error" title="Some details need fixing">Check the fields marked in red above.</Notice>
          )}
          {save.isError && !Object.keys(errors).length && <ErrorNotice error={save.error} />}
          <div className="form-actions sticky-actions">
            <Button type="submit" variant="primary" loading={save.isPending}>
              {isNew ? "Make rule" : "Save rule"}
            </Button>
            <ButtonLink to="/schedules/rules">Cancel</ButtonLink>
          </div>
        </form>
      )}
    </>
  );
}
