// Trash: deleted intro videos, kept for 30 days.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { RotateCcw, Trash2 } from "lucide-react";
import { useState } from "react";
import { api } from "../../../lib/api";
import { keys } from "../../../lib/queries";
import { formatDateTime, formatSize } from "../../../lib/format";
import { describeError } from "../../../lib/errors";
import type { TrashEntry } from "../../../lib/types";
import { Button } from "../../../components/Button";
import { ConfirmDialog } from "../../../components/Dialog";
import { EmptyState, ErrorNotice, Loading } from "../../../components/Notice";
import { useToast } from "../../../components/Toast";

const nameOf = (e: TrashEntry) => e.name || e.filename || (e.original_path ?? "").split(/[\\/]/).pop() || "Video";

export function TrashPage() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [emptying, setEmptying] = useState(false);
  const trash = useQuery({ queryKey: keys.trash, queryFn: () => api.get<{ entries: TrashEntry[]; retention_days: number }>("/prerolls/trash") });
  const refresh = () => Promise.all([queryClient.invalidateQueries({ queryKey: keys.trash }), queryClient.invalidateQueries({ queryKey: keys.prerolls })]);

  const restore = async (e: TrashEntry) => {
    try {
      await api.post(`/prerolls/trash/${e.id}/restore`, {});
      await refresh();
      toast({ tone: "success", title: `Restored "${nameOf(e)}"` });
    } catch (error) {
      toast({ tone: "error", title: describeError(error).message, description: describeError(error).hint });
    }
  };

  if (trash.isLoading) return <Loading />;
  if (trash.isError) return <ErrorNotice error={trash.error} onRetry={() => trash.refetch()} />;
  const entries = trash.data?.entries ?? [];
  return (
    <div className="stack">
      <p className="muted">Deleted videos stay here for {trash.data?.retention_days ?? 30} days, then they're removed for good.</p>
      {!entries.length ? (
        <EmptyState icon={<Trash2 size={36} />} title="Trash is empty" />
      ) : (
        <>
          <ul className="list">
            {entries.map((e) => (
              <li key={e.id} className="list-row">
                <div className="grow">
                  <strong>{nameOf(e)}</strong>
                  <div className="muted small">
                    {e.deleted_at ? `Deleted ${formatDateTime(e.deleted_at)}` : ""} {formatSize(e.size)}
                  </div>
                </div>
                <Button size="sm" icon={<RotateCcw size={16} aria-hidden="true" />} onClick={() => restore(e)}>
                  Restore
                </Button>
              </li>
            ))}
          </ul>
          <div>
            <Button variant="danger" onClick={() => setEmptying(true)}>Empty trash</Button>
          </div>
        </>
      )}
      <ConfirmDialog
        open={emptying}
        onOpenChange={setEmptying}
        title={`Delete ${entries.length === 1 ? "this video" : `these ${entries.length} videos`} for good?`}
        body={<p>This can't be undone.</p>}
        confirmLabel="Empty trash"
        danger
        onConfirm={async () => {
          await api.del("/prerolls/trash");
          await refresh();
          toast({ tone: "success", title: "Trash emptied" });
        }}
      />
    </div>
  );
}
