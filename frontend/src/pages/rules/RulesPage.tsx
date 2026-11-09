// Rules: "when this kind of title plays, play these intros", checked from
// the top down before schedules (Jellyfin and Emby, with the plugin).
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowDown, ArrowUp, ListChecks, Pencil, Plus, Trash2 } from "lucide-react";
import * as RSwitch from "@radix-ui/react-switch";
import { useNavigate } from "react-router-dom";
import { api } from "../../lib/api";
import { describeError } from "../../lib/errors";
import { ruleKeys, useRules, type Rule, type RulesResponse } from "../../lib/rules";
import { ButtonLink, IconButton } from "../../components/Button";
import { ConfirmDialog } from "../../components/Dialog";
import { EmptyState, ErrorNotice, Loading } from "../../components/Notice";
import { FeatureBadges } from "../../components/FeatureBadges";
import { useToast } from "../../components/Toast";
import { DecisionOrder, WhenHeader } from "../schedules/WhenTabs";
import { RulePreview } from "./RulePreview";
import { sharedNameIds } from "../../lib/names";
import { SharedNameHint } from "../../components/SharedNameHint";

const ruleBody = (r: Rule, enabled = r.enabled) => ({ name: r.name, enabled, when: r.when, play: r.play });

interface RowProps {
  rule: Rule;
  index: number;
  count: number;
  busy: boolean;
  onMove: (dir: -1 | 1) => void;
  onDelete: () => void;
  sharedName?: boolean;
}

function RuleRow({ rule, index, count, busy, onMove, onDelete, sharedName }: RowProps) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const toggle = useMutation({
    mutationFn: (on: boolean) => api.put<Rule>(`/api/rules/${rule.id}`, ruleBody(rule, on)),
    onSuccess: async (_d, on) => {
      await queryClient.invalidateQueries({ queryKey: ruleKeys.rules });
      toast({ tone: "success", title: on ? `"${rule.name}" is on` : `"${rule.name}" is off` });
    },
    onError: (error) => toast({ tone: "error", title: describeError(error).message, description: describeError(error).hint }),
  });
  const switchId = `rule-${rule.id}`;
  return (
    <li className={`schedule-row rule-card ${rule.enabled ? "" : "off"}`}>
      <span className="order-num" aria-label={`Checked ${index + 1} of ${count}`}>
        {index + 1}
      </span>
      <div className="grow">
        <div className="row">
          <strong>{rule.name}</strong>
          {!rule.enabled && <span className="badge">Off</span>}
        </div>
        <p className="schedule-sentence">{rule.summary}</p>
        {sharedName && <SharedNameHint kind="rule" />}
        {rule.problem && (
          <p className="rule-problem">
            <AlertTriangle size={16} aria-hidden="true" />
            <span>{rule.problem} Until that's fixed, this rule is skipped and the next one is checked.</span>
          </p>
        )}
      </div>
      <div className="schedule-actions">
        <IconButton label={`Check ${rule.name} earlier`} disabled={busy || index === 0} onClick={() => onMove(-1)}>
          <ArrowUp size={18} aria-hidden="true" />
        </IconButton>
        <IconButton label={`Check ${rule.name} later`} disabled={busy || index === count - 1} onClick={() => onMove(1)}>
          <ArrowDown size={18} aria-hidden="true" />
        </IconButton>
        <label htmlFor={switchId} className="visually-hidden">
          {rule.name} on or off
        </label>
        <RSwitch.Root id={switchId} className="switch" checked={rule.enabled} disabled={toggle.isPending} onCheckedChange={(on) => toggle.mutate(on)}>
          <RSwitch.Thumb className="switch-thumb" />
        </RSwitch.Root>
        <IconButton label={`Edit ${rule.name}`} onClick={() => navigate(`/schedules/rules/${rule.id}`)}>
          <Pencil size={18} aria-hidden="true" />
        </IconButton>
        <IconButton label={`Delete ${rule.name}`} onClick={onDelete}>
          <Trash2 size={18} aria-hidden="true" />
        </IconButton>
      </div>
    </li>
  );
}

export default function RulesPage() {
  const rules = useRules();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [deleting, setDeleting] = useState<Rule | null>(null);
  const list = rules.data?.rules ?? [];
  const shared = sharedNameIds(list);

  const reorder = useMutation({
    mutationFn: (ids: number[]) => api.put<{ rules: Rule[] }>("/api/rules/order", { ids }),
    onMutate: (ids) => {
      // Move it on screen straight away; the server's answer replaces it.
      const before = queryClient.getQueryData<RulesResponse>(ruleKeys.rules);
      if (before) {
        const byId = new Map(before.rules.map((r) => [r.id, r]));
        queryClient.setQueryData<RulesResponse>(ruleKeys.rules, { ...before, rules: ids.map((id) => byId.get(id)).filter((r): r is Rule => Boolean(r)) });
      }
      return { before };
    },
    onSuccess: (data) => {
      const current = queryClient.getQueryData<RulesResponse>(ruleKeys.rules);
      if (current) queryClient.setQueryData<RulesResponse>(ruleKeys.rules, { ...current, rules: data.rules });
    },
    onError: (error, _ids, ctx) => {
      if (ctx?.before) queryClient.setQueryData(ruleKeys.rules, ctx.before);
      toast({ tone: "error", title: "The order didn't change", description: describeError(error).message });
    },
  });

  const move = (index: number, dir: -1 | 1) => {
    const ids = list.map((r) => r.id);
    const [moved] = ids.splice(index, 1);
    if (moved === undefined) return;
    ids.splice(index + dir, 0, moved);
    reorder.mutate(ids);
  };

  const remove = async (r: Rule) => {
    await api.del(`/api/rules/${r.id}`);
    await queryClient.invalidateQueries({ queryKey: ruleKeys.rules });
    toast({ tone: "success", title: `Deleted the rule "${r.name}"` });
  };

  return (
    <>
      <WhenHeader
        helpSlug="rules"
        actions={<ButtonLink to="/schedules/rules/new" variant="primary" icon={<Plus size={18} aria-hidden="true" />}>New rule</ButtonLink>}
      />
      <DecisionOrder current={1} />
      <section className="section" aria-labelledby="rules-title">
        <div className="row-between">
          <h2 id="rules-title">Your rules</h2>
          <FeatureBadges feature="rule_sets" />
        </div>
        <p className="muted">Checked from the top down. The first rule that matches the title picks its intros.</p>
        {rules.isLoading ? (
          <Loading />
        ) : rules.isError ? (
          <ErrorNotice error={rules.error} onRetry={() => rules.refetch()} />
        ) : !list.length ? (
          <EmptyState
            icon={<ListChecks size={40} />}
            title="No rules yet"
            action={
              <div className="row">
                <ButtonLink to="/schedules/rules/new?start=kids" variant="primary">Make a Kids rule</ButtonLink>
                <ButtonLink to="/schedules/rules/new">Start from scratch</ButtonLink>
              </div>
            }
          >
            A rule plays different intros for different titles. For example, cartoon intros before anything rated G or PG, or VHS
            intros before 80s horror.
          </EmptyState>
        ) : (
          <ol className="list rule-list">
            {list.map((r, i) => (
              <RuleRow key={r.id} rule={r} index={i} count={list.length} busy={reorder.isPending} onMove={(dir) => move(i, dir)} onDelete={() => setDeleting(r)} sharedName={shared.has(r.id)} />
            ))}
          </ol>
        )}
        {rules.data?.fallback && <p className="muted small rules-fallback">{rules.data.fallback}</p>}
      </section>
      <RulePreview />
      <ConfirmDialog
        open={Boolean(deleting)}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={deleting ? `Delete the rule "${deleting.name}"?` : ""}
        body={<p>Your intro videos and collections stay. Titles this rule matched go to the next rule, or your schedules. To pause it instead, turn it off.</p>}
        confirmLabel="Delete rule"
        danger
        onConfirm={() => (deleting ? remove(deleting) : undefined)}
      />
    </>
  );
}
