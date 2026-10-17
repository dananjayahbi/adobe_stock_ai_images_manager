"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useInfiniteRecords } from "@/hooks/useInfiniteRecords";
import { useFolderHistory } from "@/hooks/useFolderHistory";
import { useMarqueeSelect } from "@/hooks/useMarqueeSelect";
import EmptyState from "@/components/ui/EmptyState";
import Button from "@/components/ui/Button";
import Modal from "@/components/ui/Modal";
import GalleryTile from "@/components/gallery/GalleryTile";
import GroupCard from "@/components/gallery/GroupCard";
import FilterBar, { type GalleryFilters } from "@/components/gallery/FilterBar";
import SelectionModeToggle from "@/components/gallery/SelectionModeToggle";
import MarqueeOverlay from "@/components/gallery/MarqueeOverlay";
import SelectionToolbar from "@/components/gallery/SelectionToolbar";
import DownloadDialog from "@/components/gallery/DownloadDialog";
import DeleteDialog from "@/components/gallery/DeleteDialog";
import GroupDialog from "@/components/gallery/GroupDialog";
import PromoteDialog from "@/components/gallery/PromoteDialog";
import LoadSentinel from "@/components/gallery/LoadSentinel";
import ViewerModal from "@/components/viewer/ViewerModal";
import { downloadRecordFile } from "@/lib/downloads";
import { downloadSelectionCsv } from "@/lib/delivery";
import { beginDrag } from "@/lib/dragPayload";
import { assignRecords, deleteGroup, fetchGroups, renameGroup } from "@/lib/groups";
import { setRecordsUsed } from "@/lib/records";
import type { GalleryGroup, ImageRecord } from "@/lib/types";

/**
 * Gallery: folders + filtered images, multi-select for download/group/delete,
 * and a full-viewport viewer.
 *
 * View model: at the top level the page lists folder cards (never filtered)
 * plus ungrouped images; opening a folder scopes the image query to it — and
 * records the folder in `?group=`, so the browser's own back button steps out
 * of the folder exactly like the Back button does.
 *
 * Selection is per-image ids and survives filter changes. In *select mode*
 * clicking a tile ticks it and dragging paints a rubber band (Windows
 * desktop convention) instead of opening the preview.
 */
export default function GalleryPage() {
  // useSearchParams needs a Suspense boundary when Next prerenders the page.
  return (
    <Suspense fallback={null}>
      <GalleryView />
    </Suspense>
  );
}

function GalleryView() {
  const [search, setSearch] = useState("");
  const [draft, setDraft] = useState("");
  const [filters, setFilters] = useState<GalleryFilters>({
    // Default lens: Any state — the gallery opens on everything the pipeline
    // holds (the old composite default hid all but a handful of records).
    // "Publishable" and the six states stay one select away.
    state: "",
    used: "all",
  });
  const [groups, setGroups] = useState<GalleryGroup[]>([]);
  const [groupsLoaded, setGroupsLoaded] = useState(false);

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [selectMode, setSelectMode] = useState(false);
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const [downloadOpen, setDownloadOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [groupDialogOpen, setGroupDialogOpen] = useState(false);
  const [promoteOpen, setPromoteOpen] = useState(false);
  const [renameTarget, setRenameTarget] = useState<GalleryGroup | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  const loadGroups = useCallback(() => {
    fetchGroups()
      .then((items) => {
        setGroups(items);
        setGroupsLoaded(true);
      })
      .catch((err) =>
        setActionError(err instanceof Error ? err.message : String(err))
      );
  }, []);

  useEffect(() => {
    loadGroups();
  }, [loadGroups]);

  // Leave selection behind whenever the folder context changes — opening a
  // folder, the Back button, or the browser's own back/forward arrows.
  const handleGroupIdChange = useCallback(() => {
    setSelected(new Set());
  }, []);

  const knownGroupIds = useMemo(
    () => (groupsLoaded ? groups.map((group) => group.id) : null),
    [groupsLoaded, groups]
  );

  const { groupId, openFolder, closeFolder, resetFolder } = useFolderHistory({
    onGroupIdChange: handleGroupIdChange,
    knownGroupIds,
  });

  const {
    items: records,
    total,
    loading,
    loadingMore,
    hasMore,
    error,
    loadMore,
    reload,
  } = useInfiniteRecords({
    pageSize: 120,
    search,
    stageUpdated: true,
    state: filters.state,
    used: filters.used,
    groupId: groupId ?? "none",
  });

  const openGroup = useMemo(
    () => groups.find((group) => group.id === groupId) ?? null,
    [groups, groupId]
  );

  /**
   * Select mode: click ticks a tile; a drag paints a rubber band over the
   * grid. Plain drags *replace* the selection with what the box touches;
   * Ctrl/Cmd-drag adds to it (the desktop convention).
   */
  const gridRef = useRef<HTMLDivElement | null>(null);
  const handleMarqueeSelect = useCallback((ids: string[], additive: boolean) => {
    setSelected((current) => {
      if (!additive) return new Set(ids);
      const next = new Set(current);
      ids.forEach((id) => next.add(id));
      return next;
    });
  }, []);

  const marquee = useMarqueeSelect({
    enabled: selectMode,
    containerRef: gridRef,
    onSelect: handleMarqueeSelect,
  });

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

  // Which mark-used buttons the selection can use. Selected ids that are no
  // longer on screen (a usage filter hid them after a reload) count for
  // nothing — `null` then hides both buttons rather than guessing.
  const selectedUsage = useMemo<"used" | "unused" | "mixed" | null>(() => {
    if (selected.size === 0) return null;
    let anyUsed = false;
    let anyUnused = false;
    let seen = 0;
    for (const record of records) {
      if (!selected.has(record.id)) continue;
      seen += 1;
      if (record.is_used) anyUsed = true;
      else anyUnused = true;
      if (anyUsed && anyUnused) return "mixed";
    }
    if (seen === 0) return null;
    return anyUsed ? "used" : "unused";
  }, [records, selected]);

  // Esc leaves select mode — but only when nothing else owns Esc (the viewer
  // and the dialogs close themselves first).
  useEffect(() => {
    if (!selectMode) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (
        activeIndex !== null ||
        downloadOpen ||
        deleteOpen ||
        groupDialogOpen ||
        promoteOpen ||
        renameTarget
      ) {
        return;
      }
      event.stopPropagation();
      setSelectMode(false);
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [selectMode, activeIndex, downloadOpen, deleteOpen, groupDialogOpen, promoteOpen, renameTarget]);

  const handleDownload = useCallback(() => {
    if (selectedIds.length === 0) return;
    // One image → direct download; many → the option dialog (task rule).
    if (selectedIds.length === 1) downloadRecordFile(selectedIds[0]);
    else setDownloadOpen(true);
  }, [selectedIds]);

  // Direct Adobe-template CSV for the selection (toolbar shortcut); failures
  // surface in the page's action-error banner like every other action here.
  const handleExportCsv = useCallback(() => {
    if (selectedIds.length === 0) return;
    downloadSelectionCsv(selectedIds).catch((err) =>
      setActionError(err instanceof Error ? err.message : String(err))
    );
  }, [selectedIds]);

  // Mark the selection used/unused in one request. Unlike delete, the
  // selection is KEPT: marking is not the end of the workflow (the operator
  // often filters by usage next), and reloading without clearing makes the
  // used-stamps reappear under the same ticks.
  const handleMarkUsage = useCallback(
    (isUsed: boolean) => {
      if (selectedIds.length === 0) return;
      setRecordsUsed(selectedIds, isUsed)
        .then(() => void reload())
        .catch((err) =>
          setActionError(err instanceof Error ? err.message : String(err))
        );
    },
    [selectedIds, reload]
  );

  const refreshAll = useCallback(() => {
    void reload();
    loadGroups();
    clearSelection();
  }, [reload, loadGroups, clearSelection]);

  // Lightest refresh for a viewer-side state change: re-run the records
  // query (the same pattern mark-used uses) so the open record picks up its
  // new state/flags — selection and the folder list stay untouched.
  const refreshAfterRecordAction = useCallback(() => {
    void reload();
  }, [reload]);

  // Drag a selected tile onto a folder card to move it (and the rest of the
  // selection) in. An unselected tile — reachable when a filter hid the rest
  // of the selection — drags itself.
  const handleTileDragStart = useCallback(
    (event: React.DragEvent, record: ImageRecord) => {
      const ids =
        selected.has(record.id) && selected.size > 1
          ? Array.from(selected)
          : [record.id];
      beginDrag(event.dataTransfer, ids);
    },
    [selected]
  );

  const handleDropOnGroup = useCallback(
    async (group: GalleryGroup, recordIds: string[]) => {
      if (recordIds.length === 0) return;
      try {
        await assignRecords(recordIds, group.id);
        refreshAll();
      } catch (err) {
        setActionError(err instanceof Error ? err.message : String(err));
      }
    },
    [refreshAll]
  );

  const confirmDeleteGroup = useCallback(
    async (group: GalleryGroup) => {
      try {
        await deleteGroup(group.id);
        if (groupId === group.id) resetFolder();
        loadGroups();
      } catch (err) {
        setActionError(err instanceof Error ? err.message : String(err));
      }
    },
    [loadGroups, groupId, resetFolder]
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

  const inFolder = groupId !== null;

  return (
    <div className="space-y-6">
      {/* Header: back/title/breadcrumb + search + filters. gap-6 so the wrapped
          controls row keeps the same 24px step as the space-y-6 sections. */}
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <p className="label-caps mb-3">The collection</p>
          {inFolder && (
            <Button
              variant="secondary"
              size="sm"
              type="button"
              onClick={closeFolder}
              className="mb-2"
            >
              ← Back
            </Button>
          )}
          <h1 className="font-display text-3xl text-ink-800">
            {inFolder ? (
              <button
                type="button"
                onClick={closeFolder}
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
                {/* openGroup resolves once the folder list loads (deep links). */}
                <span className="text-oxblood-400">
                  {openGroup?.name ?? "Folder"}
                </span>
              </>
            )}
            {total > 0 && (
              <span className="ml-3 font-stamp text-sm text-ink-400">
                {total} plates
              </span>
            )}
          </h1>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <SelectionModeToggle
            active={selectMode}
            onToggle={() => setSelectMode((value) => !value)}
          />
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
                onOpen={(g) => openFolder(g.id)}
                onRename={(g) => {
                  setRenameTarget(g);
                  setRenameValue(g.name);
                }}
                onDelete={(g) => void confirmDeleteGroup(g)}
                onDropRecords={(ids) => void handleDropOnGroup(group, ids)}
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
          {selectMode && (
            <p className="mb-3 font-stamp text-[10px] uppercase tracking-[0.14em] text-ink-400">
              Click to tick · drag a box to select · Ctrl+drag adds · drag a
              tile onto a folder to move · Esc exits
            </p>
          )}
          <div
            ref={gridRef}
            className={`relative columns-2 gap-4 sm:columns-3 lg:columns-4 xl:columns-5 2xl:columns-6 ${
              selectMode ? "cursor-crosshair select-none" : ""
            }`}
            onPointerDown={marquee.onPointerDown}
            onPointerMove={marquee.onPointerMove}
            onPointerUp={marquee.onPointerUp}
            onPointerCancel={marquee.onPointerUp}
            onClickCapture={marquee.onClickCapture}
          >
            {records.map((record) => (
              <GalleryTile
                key={record.id}
                record={record}
                onOpen={open}
                selected={selected.has(record.id)}
                onToggleSelect={toggleSelect}
                selectMode={selectMode}
                draggable={selected.has(record.id)}
                onDragStart={handleTileDragStart}
              />
            ))}
            <MarqueeOverlay rect={marquee.rect} />
          </div>
          {/* Lazy loading: the next page prefetches as this scrolls into view. */}
          <LoadSentinel hasMore={hasMore} onLoadMore={loadMore} />
          {loadingMore && (
            <p className="pb-6 text-center font-stamp text-[10px] uppercase tracking-[0.14em] text-ink-400">
              Loading more…
            </p>
          )}
        </section>
      )}

      <SelectionToolbar
        count={selected.size}
        visibleCount={records.length}
        onSelectAll={selectAll}
        onClear={clearSelection}
        onDownload={handleDownload}
        onExportCsv={handleExportCsv}
        selectedUsage={selectedUsage}
        onMarkUsage={handleMarkUsage}
        onPromote={() => setPromoteOpen(true)}
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

      <PromoteDialog
        recordIds={selectedIds}
        open={promoteOpen}
        onClose={() => setPromoteOpen(false)}
        onPromoted={() => {
          void reload();
          loadGroups();
        }}
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
        onRecordChanged={refreshAfterRecordAction}
      />
    </div>
  );
}
