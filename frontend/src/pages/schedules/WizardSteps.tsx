// The three questions of the schedule wizard.
import { useState } from "react";
import { Controller, useFormContext } from "react-hook-form";
import { Plus } from "lucide-react";
import { useCategories, usePrerolls } from "../../lib/queries";
import { MONTH_NAMES } from "../../lib/format";
import { daysInMonth, WEEKDAYS, type ScheduleDraft } from "../../lib/scheduleDraft";
import { FieldShell, TextField } from "../../components/Field";
import { Select } from "../../components/Select";
import { SwitchRow, ToggleChips } from "../../components/Controls";
import { Button } from "../../components/Button";
import { Notice } from "../../components/Notice";
import { FeatureBadges } from "../../components/FeatureBadges";
import { CollectionDialog } from "../videos/CollectionDialog";
import { usePrefs } from "../../lib/prefs";
import { HolidayFields, MonthlyFields, PlaylistPicker, SpecificFields } from "./WizardExtras";

type Errors = Partial<Record<keyof ScheduleDraft, { message?: string }>>;

function Choice({ name, value, title, desc, children }: { name: keyof ScheduleDraft; value: string; title: string; desc?: string; children?: React.ReactNode }) {
  const { register } = useFormContext<ScheduleDraft>();
  return (
    <label className="choice">
      <input type="radio" value={value} {...register(name)} />
      <span className="grow">
        <span className="choice-title">{title}</span>
        {desc && <span className="choice-desc">{desc}</span>}
        {children}
      </span>
    </label>
  );
}

export function WhatStep() {
  const { register, control, setValue, formState, watch } = useFormContext<ScheduleDraft>();
  const errors = formState.errors as Errors;
  const { advanced } = usePrefs();
  const source = watch("source");
  const categories = useCategories();
  const prerolls = usePrerolls();
  const [creating, setCreating] = useState(false);
  const options = (categories.data ?? []).filter((c) => !c.is_system).map((c) => {
    const count = (prerolls.data ?? []).filter((p) => p.categories.some((pc) => pc.id === c.id)).length;
    return { value: String(c.id), label: `${c.name} (${count} ${count === 1 ? "video" : "videos"})` };
  });
  return (
    <div className="stack">
      <TextField label="Name this schedule" placeholder="For example: Halloween" error={errors.name?.message} {...register("name")} />
      {(advanced || source === "playlist") && (
        <FieldShell label="Play from" group>
          {() => (
            <div className="choice-grid">
              <Choice name="source" value="collection" title="A collection" />
              <Choice name="source" value="playlist" title="A playlist" />
            </div>
          )}
        </FieldShell>
      )}
      {source === "playlist" ? (
        <PlaylistPicker />
      ) : (
        <>
          <Controller
            control={control}
            name="collectionId"
            render={({ field }) => (
              <Select
                label="Which collection plays?"
                value={field.value}
                onChange={field.onChange}
                options={options}
                placeholder={options.length ? "Choose a collection" : "No collections yet"}
                error={errors.collectionId?.message}
              />
            )}
          />
          <div>
            <Button size="sm" icon={<Plus size={16} aria-hidden="true" />} onClick={() => setCreating(true)}>
              New collection
            </Button>
          </div>
          <FieldShell label="How should they play?" group>
            {() => (
              <div className="stack-sm">
                <Choice name="order" value="random" title="Pick one at random each time" desc="Different intro before each movie.">
                  <FeatureBadges feature="random" />
                </Choice>
                <Choice name="order" value="in_order" title="Play them all, one after another" desc="Every video in the collection, in order.">
                  <FeatureBadges feature="sequence" />
                </Choice>
              </div>
            )}
          </FieldShell>
        </>
      )}
      <CollectionDialog
        collection={creating ? "new" : null}
        onClose={() => setCreating(false)}
        onCreated={(c) => setValue("collectionId", String(c.id), { shouldValidate: true })}
      />
    </div>
  );
}

const monthOptions = MONTH_NAMES.map((m, i) => ({ value: String(i + 1), label: m }));

function MonthDay({ label, monthName, dayName }: { label: string; monthName: "startMonth" | "endMonth"; dayName: "startDay" | "endDay" }) {
  const { register, watch, formState } = useFormContext<ScheduleDraft>();
  const errors = formState.errors as Errors;
  const days = daysInMonth(Number(watch(monthName)));
  return (
    <FieldShell label={label} group error={errors[dayName]?.message}>
      {(ids) => (
        <div className="input-row">
          <label className="visually-hidden" htmlFor={`${monthName}-sel`}>{label}: month</label>
          <select id={`${monthName}-sel`} className="input" {...register(monthName, { valueAsNumber: true })}>
            {monthOptions.map((m) => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
          </select>
          <label className="visually-hidden" htmlFor={`${dayName}-sel`}>{label}: day</label>
          <select id={`${dayName}-sel`} className="input day-select" aria-invalid={ids.invalid || undefined} aria-describedby={ids.describedBy} {...register(dayName, { valueAsNumber: true })}>
            {Array.from({ length: 31 }, (_, i) => i + 1).map((d) => (
              <option key={d} value={d} disabled={d > days}>{d}</option>
            ))}
          </select>
        </div>
      )}
    </FieldShell>
  );
}

export function WhenStep() {
  const { register, watch, control, formState } = useFormContext<ScheduleDraft>();
  const errors = formState.errors as Errors;
  const when = watch("when");
  const timeLimit = watch("timeLimit");
  return (
    <div className="stack">
      <FieldShell label="When should they play?" group>
        {() => (
          <div className="stack-sm">
            <Choice name="when" value="yearly" title="Every year, between two dates" desc="Good for holidays and seasons.">
              <FeatureBadges feature="dates" />
            </Choice>
            <Choice name="when" value="dates" title="Between two dates, once" desc="For a one-off, like a movie night." />
            <Choice name="when" value="weekly" title="On certain days of the week" desc="Like weekends only." />
            <Choice name="when" value="holiday" title="On a holiday" desc="Like Thanksgiving or Easter, whatever date it falls on.">
              <FeatureBadges feature="dates" />
            </Choice>
            <Choice name="when" value="specific" title="On certain dates every year" desc="Like December 24, 25 and 31." />
            <Choice name="when" value="monthly" title="On certain days of the month" desc="Like the 1st and the 15th." />
            <Choice name="when" value="always" title="All the time" desc="Every day, until you turn it off." />
          </div>
        )}
      </FieldShell>

      {when === "yearly" && (
        <div className="form-grid">
          <MonthDay label="From" monthName="startMonth" dayName="startDay" />
          <MonthDay label="To" monthName="endMonth" dayName="endDay" />
        </div>
      )}
      {when === "dates" && (
        <div className="form-grid">
          <TextField label="First day" type="date" error={errors.startDate?.message} {...register("startDate")} />
          <TextField label="Last day" type="date" optional help="Leave empty to keep going." error={errors.endDate?.message} {...register("endDate")} />
        </div>
      )}
      {when === "holiday" && <HolidayFields />}
      {when === "monthly" && <MonthlyFields />}
      {when === "specific" && <SpecificFields />}
      {when === "weekly" && (
        <Controller
          control={control}
          name="weekDays"
          render={({ field }) => (
            <FieldShell label="Days" group error={errors.weekDays?.message}>
              {(ids) => (
                <ToggleChips
                  describedBy={ids.describedBy}
                  options={WEEKDAYS.map((d) => ({ value: d, label: d.charAt(0).toUpperCase() + d.slice(1, 3) }))}
                  selected={field.value}
                  onChange={field.onChange}
                />
              )}
            </FieldShell>
          )}
        />
      )}

      <Controller
        control={control}
        name="timeLimit"
        render={({ field }) => (
          <SwitchRow label="Only at certain times of day" description="For example, family intros before 8 pm." checked={field.value} onChange={field.onChange} />
        )}
      />
      {timeLimit && (
        <>
          <div className="form-grid">
            <TextField label="From" type="time" error={errors.timeStart?.message} {...register("timeStart")} />
            <TextField label="Until" type="time" help="An earlier time means the next morning." error={errors.timeEnd?.message} {...register("timeEnd")} />
          </div>
          <FeatureBadges feature="time_of_day" />
        </>
      )}
    </div>
  );
}

export function OverlapStep() {
  const { register, watch, formState } = useFormContext<ScheduleDraft>();
  const errors = formState.errors as Errors;
  const overlap = watch("overlap");
  return (
    <div className="stack">
      <p className="muted">Sometimes two schedules are on at once, like "Weekends" and "Halloween". What should happen then?</p>
      <FieldShell label="If schedules overlap" group>
        {() => (
          <div className="stack-sm">
            <Choice name="overlap" value="priority" title="The more important one plays" desc="You rate this schedule from 1 to 10." />
            <Choice name="overlap" value="mix" title="Mix the intros together" desc="Videos from both schedules can play." />
            <Choice name="overlap" value="only" title="Only these intros" desc="Nothing from other schedules or your default intros plays while this one is on. The never-play list and rules still go first." />
          </div>
        )}
      </FieldShell>
      {overlap !== "mix" && (
        <TextField
          label="How important is it? (1 to 10)"
          type="number"
          inputMode="numeric"
          min={1}
          max={10}
          help="10 is the most important. Holidays usually get a higher number than everyday intros."
          error={errors.priority?.message}
          {...register("priority")}
        />
      )}
      {overlap === "only" && <Notice tone="info">If two "only these" schedules are on at the same time, the more important one plays.</Notice>}
    </div>
  );
}
