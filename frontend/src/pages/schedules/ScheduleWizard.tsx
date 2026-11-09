// New or edit schedule: three short steps with a live sentence of what will happen.
import { useEffect, useRef, useState } from "react";
import { FormProvider, useForm, type FieldErrors, type Resolver } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { Check } from "lucide-react";
import { api } from "../../lib/api";
import { keys, useCategories, useSchedules } from "../../lib/queries";
import { draftToPayload, emptyDraft, scheduleToDraft, type ScheduleDraft } from "../../lib/scheduleDraft";
import { describeDraft } from "../../lib/scheduleText";
import { scheduleSchema, STEP_FIELDS } from "../../lib/scheduleSchema";
import type { Schedule } from "../../lib/types";
import { PageHeader } from "../../components/HelpPanel";
import { Button } from "../../components/Button";
import { ErrorNotice, Loading } from "../../components/Notice";
import { applyServerFields } from "../../components/Field";
import { useToast } from "../../components/Toast";
import { OverlapStep, WhatStep, WhenStep } from "./WizardSteps";
import { usePlaylists } from "../settings/advanced/playlists/usePlaylists";
import { checkNameFree } from "../../lib/names";

const STEPS = ["What plays", "When", "If they overlap"];

export default function ScheduleWizard({ embedded, onSaved }: { embedded?: boolean; onSaved?: (s: Schedule) => void }) {
  const { id } = useParams();
  const editingId = embedded ? undefined : id;
  const schedules = useSchedules();
  const categories = useCategories();
  const playlists = usePlaylists();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast();
  const [step, setStep] = useState(0);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const existing = editingId ? schedules.data?.find((s) => String(s.id) === editingId) : undefined;

  const form = useForm<ScheduleDraft>({
    resolver: zodResolver(scheduleSchema) as unknown as Resolver<ScheduleDraft>,
    defaultValues: emptyDraft(),
    // Check on Next, not when a field loses focus: a message appearing on
    // blur moves the controls below it while the person is clicking them.
    mode: "onSubmit",
  });

  // Once a step shows problems, re-check that step as the person fixes them.
  useEffect(() => {
    const sub = form.watch((_values, { name }) => {
      if (name && Object.keys(form.formState.errors).length) void form.trigger(STEP_FIELDS[step]);
    });
    return () => sub.unsubscribe();
  }, [form, step]);

  useEffect(() => {
    if (existing) {
      const draft = scheduleToDraft(existing);
      if (draft) form.reset(draft);
    }
  }, [existing, form]);

  useEffect(() => {
    headingRef.current?.focus();
  }, [step]);

  const save = useMutation({
    mutationFn: (draft: ScheduleDraft) => {
      const payload = draftToPayload(draft, new Date(), playlists.data ?? []);
      // PUT changes only the fields sent; the payload names every field the wizard owns.
      return existing
        ? api.put<Schedule>(`/schedules/${existing.id}`, payload)
        : api.post<Schedule>("/schedules", { ...payload, is_active: true });
    },
    onSuccess: async (saved, draft) => {
      await queryClient.invalidateQueries({ queryKey: keys.schedules });
      await queryClient.invalidateQueries({ queryKey: keys.active });
      toast({ tone: "success", title: existing ? `Saved "${draft.name.trim()}"` : `Made "${draft.name.trim()}"` });
      if (onSaved) onSaved(saved);
      else navigate("/schedules");
    },
    onError: (error) => {
      if (applyServerFields(error, form.setError, ["name", "priority"], [[/holiday/i, "holidayName"], [/name/i, "name"]])) {
        // A name problem lives on the first step; show it there.
        if (form.getFieldState("name").error) setStep(0);
        return;
      }
      const fields = error instanceof Error && "fields" in error ? (error as { fields: Record<string, string> }).fields : {};
      if (fields.category_id) form.setError("collectionId", { type: "server", message: fields.category_id });
      if (fields.holiday_name) form.setError("holidayName", { type: "server", message: fields.holiday_name });
    },
  });

  // Two schedules can't share a name (case and spaces don't count).
  const nameIsFree = () => {
    const taken = checkNameFree("schedule", schedules.data, form.getValues("name"), existing?.id, existing?.name);
    if (taken) form.setError("name", { type: "taken", message: taken });
    return !taken;
  };

  const next = async () => {
    const valid = await form.trigger(STEP_FIELDS[step]);
    // Checked even when something else on the step needs fixing, so both show at once.
    const free = step !== 0 || (!form.getFieldState("name").error && nameIsFree());
    if (valid && free) setStep((s) => s + 1);
  };

  const onInvalid = (errors: FieldErrors<ScheduleDraft>) => {
    const first = STEP_FIELDS.findIndex((fields) => fields.some((f) => errors[f]));
    if (first >= 0 && first !== step) setStep(first);
  };

  const draft = form.watch();
  const collection = categories.data?.find((c) => String(c.id) === draft.collectionId)?.name;
  const playlistName = playlists.data?.find((p) => String(p.id) === draft.playlistId)?.name;
  const preview = describeDraft(draft, collection, playlistName);

  if (editingId && schedules.isLoading) return <Loading />;
  if (editingId && !existing && schedules.isSuccess) {
    return <ErrorNotice error={{}} title="That schedule doesn't exist anymore. It may have been deleted." />;
  }

  const body = (
    <FormProvider {...form}>
      <ol className="steps" aria-label="Steps">
        {STEPS.map((label, i) => (
          <li key={label} className={`step-pill ${i < step ? "done" : ""}`} aria-current={i === step ? "step" : undefined}>
            {i < step ? <Check size={14} aria-hidden="true" /> : <span aria-hidden="true">{i + 1}</span>}
            {label}
          </li>
        ))}
      </ol>
      <div className="wizard-layout">
        <form
          className="card stack"
          noValidate
          onSubmit={form.handleSubmit((d) => {
            if (!nameIsFree()) return setStep(0);
            save.mutate(d);
          }, onInvalid)}
        >
          <h2 ref={headingRef} tabIndex={-1}>
            {step === 0 ? "What should play?" : step === 1 ? "When should it play?" : "What if two schedules are on at once?"}
          </h2>
          {step === 0 && <WhatStep />}
          {step === 1 && <WhenStep />}
          {step === 2 && <OverlapStep />}
          {save.isError && !Object.keys(form.formState.errors).length && <ErrorNotice error={save.error} />}
          <div className="form-actions">
            {step > 0 && <Button onClick={() => setStep((s) => s - 1)}>Back</Button>}
            {/* Separate keys: if React reused the Next button as the submit
                button, the click that moves to the last step would also submit. */}
            {step < STEPS.length - 1 ? (
              <Button key="next" variant="primary" onClick={next}>
                Next
              </Button>
            ) : (
              <Button key="save" type="submit" variant="primary" loading={save.isPending}>
                {existing ? "Save changes" : "Save schedule"}
              </Button>
            )}
            {!embedded && (
              <Button variant="ghost" onClick={() => navigate("/schedules")}>
                Cancel
              </Button>
            )}
          </div>
        </form>
        <aside className="card preview-card" aria-live="polite" aria-label="What will happen">
          <h3>What will happen</h3>
          {preview.map((line) => (
            <p key={line}>{line}</p>
          ))}
        </aside>
      </div>
    </FormProvider>
  );

  if (embedded) return body;
  return (
    <>
      <PageHeader title={existing ? `Edit "${existing.name}"` : "New schedule"} helpSlug="schedules" />
      {body}
    </>
  );
}
