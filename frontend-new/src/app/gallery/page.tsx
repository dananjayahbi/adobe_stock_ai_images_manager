"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRecords } from "@/hooks/useRecords";
import EmptyState from "@/components/ui/EmptyState";
import Button from "@/components/ui/Button";
import Modal from "@/components/ui/Modal";
import GalleryTile from "@/components/gallery/GalleryTile";
import GroupCard from "@/components/gallery/GroupCard";
import FilterBar, { type GalleryFilters } from "@/components/gallery/FilterBar";
import SelectionToolbar from "@/components/gallery/SelectionToolbar";
import DownloadDialog from "@/components/gallery/DownloadDialog";
import DeleteDialog from "@/components/gallery/DeleteDialog";
import GroupDialog from "@/components/gallery/GroupDialog";
import ViewerModal from "@/components/viewer/ViewerModal";
import { downloadRecordFile } from "@/lib/downloads";
import { deleteGroup, fetchGroups, renameGroup } from "@/lib/groups";
import type { GalleryGroup, ImageRecord } from "@/lib/types";

/**
 * Gallery: folders + filtered images, multi-select for download/group/delete,
 * and a full-viewport viewer.
 *
 * View model: at the top level the page lists folder cards (never filtered)
 * plus ungrouped images; opening a folder scopes the image query to it.
 * Selection is per-image ids and survives filter changes.
 */
export default function GalleryPage() {
  const [search, setSearch] = useState("");
  const [draft, setDraft] = useState("");
  const [filters, setFilters] = useState<GalleryFilters>({
    stage: "",
    used: "all",
  });
  const [groups, setGroups] = useState<GalleryGroup[]>([]);
  const [openGroup, setOpenGroup] = useState<GalleryGroup | null>(null);

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const [downloadOpen, setDownloadOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [groupDialogOpen, setGroupDialogOpen] = useState(false);
  const [renameTarget, setRenameTarget] = useState<GalleryGroup | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  const { page, loading, error, reload } = useRecords({
    limit: 500,
    search,
    stageUpdated: true,
    stage: filters.stage,
    used: filters.used,
    groupId: openGroup ? openGroup.id : "none",
  });

  const records = useMemo(() => page?.items ?? [], [page]);

  const loadGroups = useCallback(() => {
    fetchGroups()
      .then(setGroups)
      .catch((err) =>
        setActionError(err instanceof Error ? err.message : String(err))
      );
  }, []);

  useEffect(() => {
    loadGroups();
  }, [loadGroups]);

  const toggleSelect = useCallback((record: ImageRecord) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(record.id)) next.delete(record.id);
      else next.add(record.id);
      return next;
    });
  }, []);

  const selectAll = useCallback(() => {
    setSelected(new Set(records.map((record) => record.id)));
  }, [records]);

  const clearSelection = useCallback(() => setSelected(new Set()), []);

  const open = useCallback(
    (record: ImageRecord) => {
      const index = records.findIndex((r) => r.id === record.id);
      if (index >= 0) setActiveIndex(index);
    },
    [records]
  );

  const navigate = useCallback(
    (direction: -1 | 1) => {
      setActiveIndex((current) => {
        if (current === null || records.length === 0) return current;
        return (current + direction + records.length) % records.length;
      });
    },
    [records.length]
  );

  const active = activeIndex !== null ? records[activeIndex] ?? null : null;
  const selectedIds = useMemo(() => Array.from(selected), [selected]);

  const handleDownload = useCallback(() => {
    if (selectedIds.length === 0) return;
    // One image → direct download; many → the option dialog (task rule).
    if (selectedIds.length === 1) downloadRecordFile(selectedIds[0]);
    else setDownloadOpen(true);
  }, [selectedIds]);

  const refreshAll = useCallback(() => {
    void reload();
    loadGroups();
    clearSelection();
  }, [reload, loadGroups, clearSelection]);

  const confirmDeleteGroup = useCallback(
    async (group: GalleryGroup) => {
      try {
        await deleteGroup(group.id);
        if (openGroup?.id === group.id) setOpenGroup(null);
        loadGroups();
      } catch (err) {
        setActionError(err instanceof Error ? err.message : String(err));
      }
    },
    [loadGroups, openGroup]
  );

  const submitRename = useCallback(async () => {
    if (!renameTarget || !renameValue.trim()) return;
    try {
      await renameGroup(renameTarget.id, renameValue.trim());
      setRenameTarget(null);
      loadGroups();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    }
  }, [renameTarget, renameValue, loadGroups]);

  const inFolder = openGroup !== null;

  return (
    <div className="space-y-6">
      {/* Header: title/breadcrumb + search + filters */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="label-caps">The collection</p>
          <h1 className="font-display text-3xl text-ink-800">
            {inFolder ? (
              <button
                type="button"
                onClick={() => {
                  setOpenGroup(null);
                  clearSelection();
                }}
                className="hover:text-oxblood-400"
              >
                Gallery
              </button>
            ) : (
              "Gallery"
            )}
            {inFolder && (
              <>
                <span className="mx-2 text-ink-400">/</span>
                <span className="text-oxblood-400">{openGroup.name}</span>
              </>
            )}
            {page && (
              <span className="ml-3 font-stamp text-sm text-ink-400">
                {page.total} plates
              </span>
            )}
          </h1>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <FilterBar filters={filters} onChange={setFilters} />
          <form
            className="flex items-center gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              setSearch(draft.trim());
            }}
          >
            <input
              type="search"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onBlur={() => setSearch(draft.trim())}
              placeholder="Search titles, keywords, filenames…"
              className="w-56 rounded-sm border border-parchment-500 bg-parchment-50 px-3 py-1.5 text-sm text-ink-800 placeholder:text-ink-400/70 focus:border-brass-400 focus:outline-none focus:ring-1 focus:ring-brass-400"
              aria-label="Search the gallery"
            />
            <Button variant="secondary" size="sm" type="submit">
              Search
            </Button>
            {search && (
              <Button
                variant="ghost"
                size="sm"
                type="button"
                onClick={() => {
                  setDraft("");
                  setSearch("");
                }}
              >
                Clear
              </Button>
            )}
          </form>
        </div>
      </div>

      {(error || actionError) && (
        <p
          className="cursor-pointer rounded-sm border border-oxblood-500/40 bg-oxblood-400/10 px-3 py-2 text-sm text-oxblood-400"
          role="alert"
          onClick={() => setActionError(null)}
        >
          {actionError ?? error}
        </p>
      )}

      {loading && records.length === 0 && (
        <div className="columns-2 gap-4 sm:columns-3 lg:columns-4 xl:columns-5 2xl:columns-6">
          {Array.from({ length: 8 }).map((_, i) => (
            <div
              key={i}
              className="frame-card mb-4 h-40 animate-pulse bg-parchment-200"
            />
          ))}
        </div>
      )}

      {!loading && records.length === 0 && groups.length === 0 && (
        <EmptyState
          glyph="◈"
          title={search ? "No plates match your search" : "The gallery is empty"}
          body={
            search
              ? "Try a different word — search covers titles, descriptions, keywords, categories and filenames."
              : "Processed images appear here as soon as a pipeline step touches them."
          }
        />
      )}

      {/* Folder cards — top level only, never hidden by filters. */}
      {!inFolder && groups.length > 0 && (
        <section aria-label="Folders">
          <p className="label-caps mb-3">Folders</p>
          <div className="columns-2 gap-4 sm:columns-3 lg:columns-4 xl:columns-5 2xl:columns-6">
            {groups.map((group) => (
              <GroupCard
                key={group.id}
                group={group}
                onOpen={(g) => {
                  setOpenGroup(g);
                  clearSelection();
                }}
                onRename={(g) => {
                  setRenameTarget(g);
                  setRenameValue(g.name);
                }}
                onDelete={(g) => void confirmDeleteGroup(g)}
              />
            ))}
          </div>
        </section>
      )}

      {!loading && records.length === 0 && inFolder && (
        <EmptyState
          glyph="◇"
          title="This folder is empty"
          body="Select images at the top level and use Group to move them in."
        />
      )}

      {records.length > 0 && (
        <section aria-label="Images">
          {!inFolder && groups.length > 0 && (
            <p className="label-caps mb-3">Ungrouped images</p>
          )}
          <div className="columns-2 gap-4 sm:columns-3 lg:columns-4 xl:columns-5 2xl:columns-6">
            {records.map((record) => (
              <GalleryTile
                key={record.id}
                record={record}
                onOpen={open}
                selected={selected.has(record.id)}
                onToggleSelect={toggleSelect}
              />
            ))}
          </div>
        </section>
      )}

      <SelectionToolbar
        count={selected.size}
        visibleCount={records.length}
        onSelectAll={selectAll}
        onClear={clearSelection}
        onDownload={handleDownload}
        onGroup={() => setGroupDialogOpen(true)}
        onDelete={() => setDeleteOpen(true)}
      />

      <DownloadDialog
        recordIds={selectedIds}
        open={downloadOpen}
        onClose={() => setDownloadOpen(false)}
      />

      <DeleteDialog
        recordIds={selectedIds}
        open={deleteOpen}
        onClose={() => setDeleteOpen(false)}
        onDeleted={refreshAll}
      />

      <GroupDialog
        recordIds={selectedIds}
        open={groupDialogOpen}
        onClose={() => setGroupDialogOpen(false)}
        onChanged={refreshAll}
      />

      {/* Rename folder */}
      <Modal
        open={renameTarget !== null}
        onClose={() => setRenameTarget(null)}
        width="max-w-sm"
        labelledBy="rename-title"
      >
        <div className="border-b border-dashed border-parchment-400 px-6 pb-3 pt-4">
          <p className="label-caps">Folder</p>
          <h2 id="rename-title" className="mt-0.5 font-display text-xl text-ink-800">
            Rename
          </h2>
        </div>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void submitRename();
          }}
          className="px-6 py-5"
        >
          <input
            value={renameValue}
            onChange={(event) => setRenameValue(event.target.value)}
            maxLength={200}
            autoFocus
            className="w-full rounded-sm border border-parchment-500 bg-parchment-50 px-3 py-2 text-sm text-ink-800 focus:border-brass-400 focus:outline-none focus:ring-1 focus:ring-brass-400"
            aria-label="Folder name"
          />
          <div className="mt-4 flex justify-end gap-2">
            <Button
              variant="ghost"
              size="sm"
              type="button"
              onClick={() => setRenameTarget(null)}
            >
              Cancel
            </Button>
            <Button size="sm" type="submit" disabled={!renameValue.trim()}>
              Save
            </Button>
          </div>
        </form>
      </Modal>

      <ViewerModal
        record={active}
        onClose={() => setActiveIndex(null)}
        onNavigate={navigate}
      />
    </div>
  );
}
