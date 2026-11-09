import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, Pencil, Plus, Trash2 } from "lucide-react";
import * as RSwitch from "@radix-ui/react-switch";
import { api } from "../../lib/api";
import { keys, useActiveScheduleIds, useSchedules } from "../../lib/queries";
import { describeSchedule } from "../../lib/scheduleText";
import { scheduleToDraft } from "../../lib/scheduleDraft";
import { formatDateTime } from "../../lib/format";
import { describeError } from "../../lib/errors";
import type { Schedule } from "../../lib/types";
import { WhenHeader } from "./WhenTabs";
import { ButtonLink, IconButton } from "../../components/Button";
import { ConfirmDialog } from "../../components/Dialog";
import { EmptyState, ErrorNotice, Loading } from "../../components/Notice";
import { useToast } from "../../components/Toast";
import { DefaultIntros } from "./DefaultIntros";
import { CalendarView } from "./CalendarView";
import { TimeZoneWarning } from "../settings/TimeZoneSection";
import { useNavigate } from "react-router-dom";
import { usePlaylists } from "../settings/advanced/playlists/usePlaylists";
import { sharedNameIds } from "../../lib/names";
import { SharedNameHint } from "../../components/SharedNameHint";

function ScheduleRow({ s, active, onDelete, playlistName, sharedName }: { s: Schedule; active: boolean; onDelete: () => void; playlistName?: string; sharedName?: boolean }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const editable = scheduleToDraft(s) !== null;
  const toggle = useMutation({
    mutationFn: (on: boolean) => api.put(`/schedules/${s.id}`, { is_active: on }),
    onSuccess: async (_d, on) => {
      await queryClient.invalidateQueries({ queryKey: keys.schedules });
      await queryClient.invalidateQueries({ queryKey: keys.active });
      toast({ tone: "success", title: on ? `"${s.name}" is on` : `"${s.name}" is off` });
    },
    onError: (error) => toast({ tone: "error", title: describeError(error).message, description: describeError(error).hint }),
  });
  const switchId = `sched-${s.id}`;
  return (
    <li className={`schedule-row ${s.is_active ? "" : "off"}`}>
      <div className="grow">
        <div className="row">
          <strong>{s.name}</strong>
          {active && <span className="badge badge-success">Playing now</span>}
          {!s.is_active && <span className="badge">Off</span>}
        </div>
        <p className="schedule-sentence">{describeSchedule(s, undefined, playlistName)}</p>
        {sharedName && <SharedNameHint kind="schedule" />}
        {s.recurrence_error ? (
          <p className="field-error">This schedule's dates can't be read. Edit it to fix them.</p>
        ) : s.is_active && s.next_run && !active ? (
          <p className="muted small">Next starts {formatDateTime(s.next_run)}</p>
        ) : null}
      </div>
      <div className="schedule-actions">
        <label htmlFor={switchId} className="visually-hidden">
          {s.name} on or off
        </label>
        <RSwitch.Root id={switchId} className="switch" checked={s.is_active} disabled={toggle.isPending} onCheckedChange={(on) => toggle.mutate(on)}>
          <RSwitch.Thumb className="switch-thumb" />
        </RSwitch.Root>
        <IconButton
          label={editable ? `Edit ${s.name}` : `${s.name} was made with options this page doesn't have, so it can't be changed here.`}
          onClick={() => editable && navigate(`/schedules/${s.id}/edit`)}
          disabled={!editable}
        >
          <Pencil size={18} aria-hidden="true" />
        </IconButton>
        <IconButton label={`Delete ${s.name}`} onClick={onDelete}>
          <Trash2 size={18} aria-hidden="true" />
        </IconButton>
      </div>
    </li>
  );
}

export default function SchedulesPage() {
  const schedules = useSchedules();
  const active = useActiveScheduleIds();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [view, setView] = useState<"list" | "calendar">("list");
  const [deleting, setDeleting] = useState<Schedule | null>(null);
  const playlists = usePlaylists();
  const playlistName = (s: Schedule) => playlists.data?.find((p) => p.id === s.source_sequence_id)?.name;

  const remove = async (s: Schedule) => {
    await api.del(`/schedules/${s.id}`);
    await queryClient.invalidateQueries({ queryKey: keys.schedules });
    toast({ tone: "success", title: `Deleted "${s.name}"` });
  };

  const list = schedules.data ?? [];
  const shared = sharedNameIds(list);
  return (
    <>
      <WhenHeader
        actions={<ButtonLink to="/schedules/new" variant="primary" icon={<Plus size={18} aria-hidden="true" />}>New schedule</ButtonLink>}
      />
      <TimeZoneWarning />
      <section className="section" aria-labelledby="sched-title">
        <div className="row-between">
          <h2 id="sched-title">Your schedules</h2>
          <div className="row" role="group" aria-label="View">
            <button type="button" className="tab" data-state={view === "list" ? "active" : undefined} aria-pressed={view === "list"} onClick={() => setView("list")}>
              List
            </button>
            <button type="button" className="tab" data-state={view === "calendar" ? "active" : undefined} aria-pressed={view === "calendar"} onClick={() => setView("calendar")}>
              Calendar
            </button>
          </div>
        </div>
        {schedules.isLoading ? (
          <Loading />
        ) : schedules.isError ? (
          <ErrorNotice error={schedules.error} onRetry={() => schedules.refetch()} />
        ) : !list.length ? (
          <EmptyState
            icon={<CalendarClock size={40} />}
            title="No schedules yet"
            action={<ButtonLink to="/schedules/new" variant="primary">Make your first schedule</ButtonLink>}
          >
            A schedule says when a collection plays, like "Halloween intros every day in October".
          </EmptyState>
        ) : view === "calendar" ? (
          <CalendarView schedules={list} playlistName={playlistName} />
        ) : (
          <ul className="list">
            {list.map((s) => (
              <ScheduleRow key={s.id} s={s} active={(active.data ?? []).includes(s.id)} onDelete={() => setDeleting(s)} playlistName={playlistName(s)} sharedName={shared.has(s.id)} />
            ))}
          </ul>
        )}
      </section>
      <DefaultIntros />
      <ConfirmDialog
        open={Boolean(deleting)}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={deleting ? `Delete "${deleting.name}"?` : ""}
        body={<p>The intro videos stay in your library. Only this schedule goes, and this can't be undone. To pause it instead, turn it off.</p>}
        confirmLabel="Delete schedule"
        danger
        onConfirm={() => (deleting ? remove(deleting) : undefined)}
      />
    </>
  );
}
