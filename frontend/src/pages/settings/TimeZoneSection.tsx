// Time zone: schedules start and stop on Prerolls Max's clock. Flags when
// that clock differs from this browser's.
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { keys, useTimezone } from "../../lib/queries";
import { browserTimeZone, zonesDiffer, zoneTimeLabel } from "../../lib/timezones";
import { FieldShell } from "../../components/Field";
import { Button } from "../../components/Button";
import { ErrorNotice, Loading, Notice } from "../../components/Notice";
import { useToast } from "../../components/Toast";

export function TimeZoneWarning() {
  const zone = useTimezone();
  const browser = browserTimeZone();
  if (!zone.data || !browser || !zonesDiffer(zone.data)) return null;
  return (
    <div className="section">
      <Notice tone="warning" title="Prerolls Max's clock doesn't match yours">
        <p>
          Prerolls Max uses {zone.data} ({zoneTimeLabel(zone.data)}), but this device is on {browser} (
          {zoneTimeLabel(browser)}). Schedules start and stop on Prerolls Max's clock.{" "}
          <Link to="/settings#time-zone">Change the time zone</Link>
        </p>
      </Notice>
    </div>
  );
}

export function TimeZoneSection() {
  const zone = useTimezone();
  const list = useQuery({
    queryKey: ["timezones"],
    queryFn: async () => (await api.get<{ timezones: { value: string; label: string }[] }>("/settings/timezones")).timezones,
    staleTime: Infinity,
  });
  const queryClient = useQueryClient();
  const toast = useToast();
  const [value, setValue] = useState("");
  useEffect(() => {
    if (zone.data) setValue(zone.data);
  }, [zone.data]);

  const save = useMutation({
    mutationFn: (timezone: string) => api.put("/settings/timezone", { timezone }),
    onSuccess: async (_d, timezone) => {
      await queryClient.invalidateQueries({ queryKey: keys.timezone });
      toast({ tone: "success", title: `Time zone set to ${timezone}` });
    },
  });

  if (zone.isLoading || list.isLoading) return <Loading />;
  if (zone.isError) return <ErrorNotice error={zone.error} onRetry={() => zone.refetch()} />;

  const browser = browserTimeZone();
  const differs = zone.data ? zonesDiffer(zone.data) : false;
  const known = (list.data ?? []).some((z) => z.value === value);

  return (
    <div className="stack">
      {differs && browser && (
        <Notice tone="warning" title="This doesn't match this device">
          <p>
            This device is on {browser}. If that's where you live, use it so schedules start when you expect.
          </p>
          <Button size="sm" onClick={() => save.mutate(browser)} loading={save.isPending}>
            Use {browser}
          </Button>
        </Notice>
      )}
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          if (known) save.mutate(value);
        }}
      >
        <FieldShell
          label="Time zone"
          help="Schedules start and stop on this clock."
          error={value && !known ? "Pick a time zone from the list." : undefined}
        >
          {(ids) => (
            <select
              id={ids.id}
              className="input"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              aria-invalid={ids.invalid || undefined}
              aria-describedby={ids.describedBy}
            >
              {(list.data ?? []).map((z) => (
                <option key={z.value} value={z.value}>
                  {z.label}
                </option>
              ))}
            </select>
          )}
        </FieldShell>
        {save.isError && <ErrorNotice error={save.error} />}
        <div className="form-actions">
          <Button type="submit" variant="primary" loading={save.isPending}>
            Save time zone
          </Button>
        </div>
      </form>
    </div>
  );
}
