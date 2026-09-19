"use client";

import { Loader2, ImageOff } from "lucide-react";
import type { ReactNode } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import type { ImageRecord } from "@/lib/api";
import { cn } from "@/lib/cn";

import RecordCard from "./RecordCard";

export interface RecordGridProps {
  records: ImageRecord[];
  isLoading?: boolean;
  isSelected: (id: string) => boolean;
  onToggleSelect: (id: string) => void;
  onInspect: (record: ImageRecord) => void;
  /** Highlighted while a batch is running. */
  runningIds?: string[];
  emptyTitle?: string;
  emptyDescription?: string;
  emptyAction?: ReactNode;
  className?: string;
}

/**
 * Responsive record grid.
 *
 * Column count scales with the viewport all the way to 6 on very wide
 * displays, which is what makes the full-width layout worthwhile.
 */
export function RecordGrid({
  records,
  isLoading = false,
  isSelected,
  onToggleSelect,
  onInspect,
  runningIds,
  emptyTitle = "Nothing here yet",
  emptyDescription,
  emptyAction,
  className,
}: RecordGridProps) {
  if (isLoading && records.length === 0) {
    return (
      <div className="flex items-center justify-center gap-2 rounded-xl border border-navy-700/40 bg-navy-850/30 py-16 text-sm text-navy-400">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
        Loading records…
      </div>
    );
  }

  if (records.length === 0) {
    return (
      <EmptyState
        icon={<ImageOff className="h-5 w-5" aria-hidden />}
        title={emptyTitle}
        description={emptyDescription}
        action={emptyAction}
      />
    );
  }

  const running = new Set(runningIds ?? []);

  return (
    <div
      className={cn(
        "grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6",
        className
      )}
    >
      {records.map((record) => (
        <RecordCard
          key={record.id}
          record={record}
          isSelected={isSelected(record.id)}
          isRunning={running.has(record.id)}
          onToggleSelect={onToggleSelect}
          onInspect={onInspect}
        />
      ))}
    </div>
  );
}

export default RecordGrid;
