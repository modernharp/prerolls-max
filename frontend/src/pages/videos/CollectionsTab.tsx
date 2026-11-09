// Collections: groups of intro videos that schedules play from.
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FolderOpen, Pencil, Plus, Trash2 } from "lucide-react";
import { api } from "../../lib/api";
import { keys, useCategories, usePrerolls } from "../../lib/queries";
import { plural } from "../../lib/format";
import type { Category } from "../../lib/types";
import { Button, IconButton } from "../../components/Button";
import { ConfirmDialog } from "../../components/Dialog";
import { EmptyState, ErrorNotice, Loading, Notice } from "../../components/Notice";
import { useToast } from "../../components/Toast";
import { CollectionDialog } from "./CollectionDialog";

interface DeleteImpact {
  preroll_count: number;
  becoming_uncategorized: number;
  schedule_count: number;
  schedule_fallback_count: number;
  is_filler_in_setting: boolean;
}

function DeleteBody({ category }: { category: Category }) {
  const impact = useQuery({
    queryKey: ["delete-impact", category.id],
    queryFn: () => api.get<DeleteImpact>(`/categories/${category.id}/delete-impact`),
  });
  if (impact.isLoading) return <Loading label="Checking what uses it…" />;
  const i = impact.data;
  return (
    <>
      <p>The videos stay in your library. Only the collection goes, and this can't be undone.</p>
      {i && i.becoming_uncategorized > 0 && <p>{plural(i.becoming_uncategorized, "video")} will no longer be in any collection.</p>}
      {i && i.schedule_count > 0 && (
        <Notice tone="warning">{plural(i.schedule_count, "schedule")} play this collection and will be turned off.</Notice>
      )}
      {i?.is_filler_in_setting && <Notice tone="warning">It's your default intros collection. Default intros will stop until you pick another.</Notice>}
    </>
  );
}

export function CollectionsTab() {
  const categories = useCategories();
  const prerolls = usePrerolls();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [editing, setEditing] = useState<Category | "new" | null>(null);
  const [deleting, setDeleting] = useState<Category | null>(null);

  if (categories.isLoading) return <Loading />;
  if (categories.isError) return <ErrorNotice error={categories.error} onRetry={() => categories.refetch()} />;

  const counts = new Map<number, number>();
  for (const p of prerolls.data ?? []) for (const c of p.categories) counts.set(c.id, (counts.get(c.id) ?? 0) + 1);
  const list = (categories.data ?? []).filter((c) => !c.is_system);

  const remove = async (c: Category) => {
    await api.del(`/categories/${c.id}`);
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: keys.categories }),
      queryClient.invalidateQueries({ queryKey: keys.prerolls }),
      queryClient.invalidateQueries({ queryKey: keys.schedules }),
    ]);
    toast({ tone: "success", title: `Deleted the "${c.name}" collection` });
  };

  return (
    <>
      <div className="row-between section-gap">
        <p className="muted grow">Put videos in collections, like "Halloween" or "Everyday", then choose when each collection plays.</p>
        <Button variant="primary" icon={<Plus size={18} aria-hidden="true" />} onClick={() => setEditing("new")}>
          New collection
        </Button>
      </div>
      {!list.length ? (
        <EmptyState
          icon={<FolderOpen size={40} />}
          title="No collections yet"
          action={<Button variant="primary" onClick={() => setEditing("new")}>Make your first collection</Button>}
        >
          A collection is a group of intro videos. You'll pick a collection when you choose when intros play.
        </EmptyState>
      ) : (
        <ul className="list">
          {list.map((c) => (
            <li key={c.id} className="list-row">
              <FolderOpen size={24} aria-hidden="true" className="muted" />
              <div className="grow">
                <strong>{c.name}</strong>
                <div className="muted small">
                  {plural(counts.get(c.id) ?? 0, "video")}
                  {c.description ? ` · ${c.description}` : ""}
                </div>
              </div>
              <IconButton label={`Edit ${c.name}`} onClick={() => setEditing(c)}>
                <Pencil size={18} aria-hidden="true" />
              </IconButton>
              <IconButton label={`Delete ${c.name}`} onClick={() => setDeleting(c)}>
                <Trash2 size={18} aria-hidden="true" />
              </IconButton>
            </li>
          ))}
        </ul>
      )}
      <CollectionDialog collection={editing} onClose={() => setEditing(null)} />
      <ConfirmDialog
        open={Boolean(deleting)}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={deleting ? `Delete the "${deleting.name}" collection?` : ""}
        body={deleting ? <DeleteBody category={deleting} /> : null}
        confirmLabel="Delete collection"
        danger
        onConfirm={() => (deleting ? remove(deleting) : undefined)}
      />
    </>
  );
}
