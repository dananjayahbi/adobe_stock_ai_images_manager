"use client";

import { CheckCircle2, Circle, Download, Table, Trash2 } from "lucide-react";

import CsvExportActions from "@/components/stages/delivery/CsvExportActions";
import type { UsageFilter } from "@/lib/api";
import type { StatusScope } from "./useGalleryRecords";

interface GalleryToolbarProps {
  usageFilter: UsageFilter;
  onUsageFilterChange: (value: UsageFilter) => void;
  statusScope: StatusScope;
  onStatusScopeChange: (value: StatusScope) => void;
  counts: Record<UsageFilter, number>;
  selectedCount: number;
  visibleCount: number;
  isBusy: boolean;
  onSelectAll: () => void;
  onClearSelection: () => void;
  onMarkUsed: () => void;
  onMarkUnused: () => void;
  onGenerateTable: () => void;
  onBulkDelete: () => void;
  /** Ids of the selected records, for the CSV/bundle actions. */
  selectedIds: string[];
  onCsvError: (message: string | null) => void;
  onCsvNotice: (message: string | null) => void;
}

const USAGE_FILTERS: { key: UsageFilter; label: string }[] = [
  { key: "unused", label: "Unused" },
  { key: "used", label: "Used" },
  { key: "all", label: "All" },
];

const SCOPES: { key: StatusScope; label: string }[] = [
  { key: "ready", label: "Upload-ready" },
  { key: "all", label: "All states" },
];

/** Filter chips plus the bulk-action bar for the gallery. */
export default function GalleryToolbar({
  usageFilter,
  onUsageFilterChange,
  statusScope,
  onStatusScopeChange,
  counts,
  selectedCount,
  visibleCount,
  isBusy,
  onSelectAll,
  onClearSelection,
  onMarkUsed,
  onMarkUnused,
  onGenerateTable,
  onBulkDelete,
  selectedIds,
  onCsvError,
  onCsvNotice,
}: GalleryToolbarProps) {
  const hasSelection = selectedCount > 0;
  const allSelected = visibleCount > 0 && selectedCount >= visibleCount;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {USAGE_FILTERS.map(({ key, label }) => {
          const isActive = usageFilter === key;
          return (
            <button
              key={key}
              type="button"
              onClick={() => onUsageFilterChange(key)}
              className={`rounded-full border px-3.5 py-1.5 text-xs font-medium transition-colors ${
                isActive
                  ? "border-accent-500 bg-accent-500/15 text-accent-300"
                  : "border-navy-700 text-navy-300 hover:border-navy-400 hover:text-navy-100"
              }`}
            >
              {label}
              <span className="ml-1.5 opacity-70">{counts[key]}</span>
            </button>
          );
        })}

        <span className="mx-1 h-5 w-px bg-navy-800" aria-hidden />

        {SCOPES.map(({ key, label }) => {
          const isActive = statusScope === key;
          return (
            <button
              key={key}
              type="button"
              onClick={() => onStatusScopeChange(key)}
              className={`rounded-full border px-3.5 py-1.5 text-xs font-medium transition-colors ${
                isActive
                  ? "border-violet-500 bg-violet-500/15 text-violet-300"
                  : "border-navy-700 text-navy-300 hover:border-navy-400 hover:text-navy-100"
              }`}
            >
              {label}
            </button>
          );
        })}

        <span className="ml-auto text-xs text-navy-400">
          {visibleCount} shown
          {hasSelection ? ` · ${selectedCount} selected` : ""}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-navy-800 bg-navy-900/50 px-3 py-2">
        <button
          type="button"
          onClick={allSelected ? onClearSelection : onSelectAll}
          disabled={visibleCount === 0}
          className="rounded-md border border-navy-700 px-3 py-1.5 text-xs font-medium text-navy-200 transition-colors hover:border-navy-400 hover:text-navy-50 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {allSelected ? "Clear selection" : "Select all"}
        </button>

        <span className="h-5 w-px bg-navy-800" aria-hidden />

        <ToolbarAction
          label="Mark used"
          icon={<CheckCircle2 className="h-3.5 w-3.5" />}
          disabled={!hasSelection || isBusy}
          onClick={onMarkUsed}
        />
        <ToolbarAction
          label="Mark unused"
          icon={<Circle className="h-3.5 w-3.5" />}
          disabled={!hasSelection || isBusy}
          onClick={onMarkUnused}
        />
        {/* No plain "Download ZIP" here: the delivery bar below offers
            "ZIP + CSV", which is a superset. Two ZIP buttons that differ only
            in whether the CSV is inside would be a coin flip for the operator. */}
        <ToolbarAction
          label="Generate upload table"
          icon={<Table className="h-3.5 w-3.5" />}
          disabled={!hasSelection || isBusy}
          onClick={onGenerateTable}
          emphasis
        />
        <ToolbarAction
          label="Delete"
          icon={<Trash2 className="h-3.5 w-3.5" />}
          disabled={!hasSelection || isBusy}
          onClick={onBulkDelete}
          danger
        />
      </div>

      {/* CSV / ZIP live in their own bar rather than beside the usage actions:
          they are the *delivery* step, and the operator reaches for them when
          the batch is final, not while triaging. The gallery exports published
          assets, so `onlyReady={false}` keeps the server's ready-only filter
          from silently emptying the CSV. */}
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-navy-800 bg-navy-900/50 px-3 py-2">
        <span className="text-[11px] font-medium uppercase tracking-wide text-navy-400">
          Adobe delivery
        </span>
        <CsvExportActions
          selectedIds={selectedIds}
          onlyReady={false}
          disabled={isBusy}
          onError={onCsvError}
          onNotice={onCsvNotice}
        />
        <span className="ml-auto text-[11px] text-navy-500">
          CSV lists the selected rows; ZIP bundles them with that CSV.
        </span>
      </div>
    </div>
  );
}

function ToolbarAction({
  label,
  icon,
  onClick,
  disabled = false,
  danger = false,
  emphasis = false,
}: {
  label: string;
  icon: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
  emphasis?: boolean;
}) {
  const tone = danger
    ? "border-red-500/40 bg-red-500/10 text-red-300 hover:border-red-400 hover:text-red-100"
    : emphasis
      ? "border-accent-500/50 bg-accent-500/15 text-accent-300 hover:border-accent-400 hover:text-accent-100"
      : "border-navy-700 text-navy-200 hover:border-navy-400 hover:text-navy-50";

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${tone}`}
    >
      {icon}
      {label}
    </button>
  );
}
