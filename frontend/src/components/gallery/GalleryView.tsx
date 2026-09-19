"use client";

import { AlertCircle, CheckCircle2, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import ConfirmDialog from "@/components/ConfirmDialog";
import { getDownloadUrl, type ImageRecord } from "@/lib/api";
import { saveUploadTableSelection } from "@/lib/uploadTableStore";

import GalleryMasonryGrid from "./GalleryMasonryGrid";
import GalleryPreviewModal from "./GalleryPreviewModal";
import GalleryToolbar from "./GalleryToolbar";
import { useGalleryRecords } from "./useGalleryRecords";
import { useGallerySelection } from "./useGallerySelection";

type PendingDelete = { kind: "one"; record: ImageRecord } | { kind: "many" };

/** Full gallery experience: filters, multi-select, downloads, and the upload table. */
export default function GalleryView() {
  const gallery = useGalleryRecords();
  const selection = useGallerySelection();
  const [previewRecord, setPreviewRecord] = useState<ImageRecord | null>(null);
  const [pendingDelete, setPendingDelete] = useState<PendingDelete | null>(null);

  const { prune } = selection;
  useEffect(() => {
    prune(gallery.availableIds);
  }, [gallery.availableIds, prune]);

  // Keep the preview modal in sync with polling refreshes.
  useEffect(() => {
    if (!previewRecord) return;
    const refreshed = gallery.records.find((r) => r.id === previewRecord.id);
    if (!refreshed) {
      setPreviewRecord(null);
    } else if (refreshed !== previewRecord) {
      setPreviewRecord(refreshed);
    }
  }, [gallery.records, previewRecord]);

  // Auto-dismiss transient success notices.
  useEffect(() => {
    if (!gallery.notice) return;
    const timer = setTimeout(() => gallery.clearNotice(), 3000);
    return () => clearTimeout(timer);
  }, [gallery.notice, gallery.clearNotice]);

  const handleSelectAll = useCallback(() => {
    selection.selectMany(gallery.availableIds);
  }, [selection, gallery.availableIds]);

  const handleGenerateTable = useCallback(() => {
    const ids = selection.selectedIds;
    if (ids.length === 0) return;
    const token = saveUploadTableSelection(ids);
    window.open(`/upload-table?token=${encodeURIComponent(token)}`, "_blank", "noopener");
  }, [selection.selectedIds]);

  const handleDownload = useCallback(
    (record: ImageRecord) => {
      window.open(getDownloadUrl(record.id), "_blank", "noopener");
    },
    []
  );

  const handleDownloadZip = useCallback(() => {
    void gallery.downloadZip(selection.selectedIds);
  }, [gallery, selection.selectedIds]);

  const confirmDelete = useCallback(async () => {
    if (!pendingDelete) return;
    if (pendingDelete.kind === "one") {
      await gallery.removeOne(pendingDelete.record);
      setPreviewRecord(null);
    } else {
      await gallery.removeMany(selection.selectedIds);
    }
    selection.clear();
    setPendingDelete(null);
  }, [pendingDelete, gallery, selection]);

  const deleteMessage = useMemo(() => {
    if (!pendingDelete) return "";
    if (pendingDelete.kind === "one") {
      return `“${pendingDelete.record.generated_title || pendingDelete.record.filename}” and its staged file will be permanently removed.`;
    }
    return `${selection.count} selected image(s), their thumbnails, and any staged upload files will be permanently removed.`;
  }, [pendingDelete, selection.count]);

  return (
    <div className="space-y-5">
      {gallery.error && (
        <Banner
          tone="error"
          onDismiss={() => gallery.setError(null)}
          icon={<AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />}
        >
          {gallery.error}
        </Banner>
      )}

      {gallery.notice && (
        <Banner
          tone="success"
          onDismiss={gallery.clearNotice}
          icon={<CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />}
        >
          {gallery.notice}
        </Banner>
      )}

      <GalleryToolbar
        usageFilter={gallery.usageFilter}
        onUsageFilterChange={gallery.setUsageFilter}
        statusScope={gallery.statusScope}
        onStatusScopeChange={gallery.setStatusScope}
        counts={gallery.counts}
        selectedCount={selection.count}
        visibleCount={gallery.availableIds.length}
        isBusy={gallery.isBusy}
        onSelectAll={handleSelectAll}
        onClearSelection={selection.clear}
        onMarkUsed={() => void gallery.markUsed(selection.selectedIds, true)}
        onMarkUnused={() => void gallery.markUsed(selection.selectedIds, false)}
        onDownloadZip={handleDownloadZip}
        onGenerateTable={handleGenerateTable}
        onBulkDelete={() => setPendingDelete({ kind: "many" })}
      />

      <GalleryMasonryGrid
        records={gallery.records}
        isLoading={gallery.isLoading}
        isSelected={selection.isSelected}
        onToggleSelect={selection.toggle}
        onPreview={setPreviewRecord}
        onToggleUsed={(record) => void gallery.toggleUsed(record)}
        onDownload={handleDownload}
        onDelete={(record) => setPendingDelete({ kind: "one", record })}
      />

      <GalleryPreviewModal
        record={previewRecord}
        onClose={() => setPreviewRecord(null)}
        onToggleUsed={(record) => void gallery.toggleUsed(record)}
        onDownload={handleDownload}
        onDelete={(record) => setPendingDelete({ kind: "one", record })}
      />

      <ConfirmDialog
        isOpen={pendingDelete !== null}
        title="Delete image(s)?"
        message={deleteMessage}
        confirmLabel={pendingDelete?.kind === "many" ? "Delete selected" : "Delete"}
        isBusy={gallery.isBusy}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}

function Banner({
  tone,
  icon,
  children,
  onDismiss,
}: {
  tone: "error" | "success";
  icon: React.ReactNode;
  children: React.ReactNode;
  onDismiss: () => void;
}) {
  const styles =
    tone === "error"
      ? "border-red-500/40 bg-red-500/10 text-red-200"
      : "border-emerald-500/40 bg-emerald-500/10 text-emerald-200";

  return (
    <div className={`flex items-start gap-2 rounded-lg border px-4 py-3 text-sm ${styles}`}>
      {icon}
      <span className="flex-1">{children}</span>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss message"
        className="rounded p-0.5 opacity-70 transition-opacity hover:opacity-100"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
