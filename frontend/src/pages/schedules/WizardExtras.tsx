// More answers for the schedule wizard: a holiday, days of the month, dates
// every year, and (Advanced) a playlist instead of a collection.
import { useQuery } from "@tanstack/react-query";
import { Controller, useFormContext } from "react-hook-form";
import { api } from "../../lib/api";
import { MONTH_NAMES, formatDay } from "../../lib/format";
import type { ScheduleDraft } from "../../lib/scheduleDraft";
import { FieldShell } from "../../components/Field";
import { Select } from "../../components/Select";
import { ToggleChips } from "../../components/Controls";
import { ErrorNotice, Loading } from "../../components/Notice";
import { usePlaylists } from "../settings/advanced/playlists/usePlaylists";

type Errors = Partial<Record<keyof ScheduleDraft, { message?: string }>>;

interface Holiday {
  date: string;
  name: string;
  localName: string;
}

export function HolidayFields() {
  const { control, watch, setValue, formState } = useFormContext<ScheduleDraft>();
  const errors = formState.errors as Errors;
  const country = watch("holidayCountry");
  const year = new Date().getFullYear();
  const countries = useQuery({
    queryKey: ["holiday-countries"],
    queryFn: async () => (await api.get<{ countries: { countryCode: string; name: string }[] }>("/holiday-api/countries")).countries,
    staleTime: Infinity,
  });
  const holidays = useQuery({
    queryKey: ["holidays", country, year],
    enabled: Boolean(country),
    staleTime: 60 * 60_000,
    queryFn: async () => {
      const [now, next] = await Promise.all([
        api.get<{ holidays: Holiday[] }>(`/holiday-api/holidays/${country}/${year}`),
        api.get<{ holidays: Holiday[] }>(`/holiday-api/holidays/${country}/${year + 1}`).catch(() => ({ holidays: [] as Holiday[] })),
      ]);
      // One row per holiday, with its next date.
      const today = new Date().toISOString().slice(0, 10);
      const byName = new Map<string, Holiday>();
      for (const h of [...now.holidays, ...next.holidays]) {
        if (h.date < today || byName.has(h.name)) continue;
        byName.set(h.name, h);
      }
      for (const h of now.holidays) if (!byName.has(h.name)) byName.set(h.name, h);
      return [...byName.values()].sort((a, b) => a.date.localeCompare(b.date));
    },
  });
  if (countries.isError) return <ErrorNotice error={countries.error} onRetry={() => countries.refetch()} />;
  return (
    <div className="form-grid">
      <Controller
        control={control}
        name="holidayCountry"
        render={({ field }) => (
          <Select
            label="Country"
            value={field.value}
            onChange={(v) => {
              field.onChange(v);
              setValue("holidayName", "");
            }}
            options={(countries.data ?? []).map((c) => ({ value: c.countryCode, label: c.name }))}
            placeholder={countries.isLoading ? "Loading…" : "Choose a country"}
            error={errors.holidayCountry?.message}
          />
        )}
      />
      {holidays.isLoading ? (
        <Loading label="Loading holidays…" />
      ) : holidays.isError ? (
        <ErrorNotice error={holidays.error} onRetry={() => holidays.refetch()} />
      ) : (
        <Controller
          control={control}
          name="holidayName"
          render={({ field }) => (
            <Select
              label="Holiday"
              help="It plays on that day each year, whatever date the holiday falls on."
              value={field.value}
              onChange={field.onChange}
              options={(holidays.data ?? []).map((h) => ({
                value: h.name,
                label: `${h.name}${h.localName && h.localName !== h.name ? ` (${h.localName})` : ""}, next on ${formatDay(h.date, true)}`,
              }))}
              placeholder="Choose a holiday"
              error={errors.holidayName?.message}
            />
          )}
        />
      )}
    </div>
  );
}

const DAY_OPTIONS = Array.from({ length: 31 }, (_, i) => ({ value: i + 1, label: String(i + 1) }));
const MONTH_OPTIONS = MONTH_NAMES.map((m, i) => ({ value: i + 1, label: m.slice(0, 3) }));

export function MonthlyFields() {
  const { control, formState } = useFormContext<ScheduleDraft>();
  const errors = formState.errors as Errors;
  return (
    <>
      <Controller
        control={control}
        name="monthDays"
        render={({ field }) => (
          <FieldShell label="Days of the month" group help="Days a month doesn't have are skipped, like the 31st in April." error={errors.monthDays?.message}>
            {(ids) => <ToggleChips describedBy={ids.describedBy} options={DAY_OPTIONS} selected={field.value} onChange={field.onChange} />}
          </FieldShell>
        )}
      />
      <Controller
        control={control}
        name="months"
        render={({ field }) => (
          <FieldShell label="In these months" optional group help="Pick none for every month.">
            {(ids) => <ToggleChips describedBy={ids.describedBy} options={MONTH_OPTIONS} selected={field.value} onChange={field.onChange} />}
          </FieldShell>
        )}
      />
    </>
  );
}

export function SpecificFields() {
  const { control, register, formState } = useFormContext<ScheduleDraft>();
  const errors = formState.errors as Errors;
  return (
    <>
      <div className="field">
        <label className="field-label" htmlFor="specific-month">
          Month
        </label>
        <select id="specific-month" className="input" {...register("specificMonth", { valueAsNumber: true })}>
          {MONTH_NAMES.map((m, i) => (
            <option key={m} value={i + 1}>
              {m}
            </option>
          ))}
        </select>
      </div>
      <Controller
        control={control}
        name="specificDays"
        render={({ field }) => (
          <FieldShell label="Dates" group help="For example 24, 25 and 31 in December." error={errors.specificDays?.message}>
            {(ids) => <ToggleChips describedBy={ids.describedBy} options={DAY_OPTIONS} selected={field.value} onChange={field.onChange} />}
          </FieldShell>
        )}
      />
    </>
  );
}

export function PlaylistPicker() {
  const { control, formState } = useFormContext<ScheduleDraft>();
  const errors = formState.errors as Errors;
  const playlists = usePlaylists();
  const options = (playlists.data ?? []).map((p) => ({ value: String(p.id), label: p.name }));
  return (
    <Controller
      control={control}
      name="playlistId"
      render={({ field }) => (
        <Select
          label="Which playlist plays?"
          value={field.value}
          onChange={field.onChange}
          options={options}
          placeholder={playlists.isLoading ? "Loading…" : options.length ? "Choose a playlist" : "No playlists yet"}
          help="Make playlists in Settings, Advanced, Playlists."
          error={errors.playlistId?.message}
        />
      )}
    />
  );
}
