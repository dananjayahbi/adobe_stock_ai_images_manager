"use client";

import { FileImage, Loader2, UploadCloud } from "lucide-react";
import { useState, type DragEvent } from "react";

import { ProgressBar } from "@/components/ui/ProgressBar";
import { cn } from "@/lib/cn";
import { isPromptDrag } from "@/lib/promptDrag";
import { useImageUpload } from "@/hooks/useImageUpload";

export interface GalleryUploadSlotProps {
  /** Called after a successful upload so the page can refresh its records. */
  onUploaded: (count: number) => void;
  disabled?: boolean;
}

/**
 * The upload slot that sits **first in the image grid**.
 *
 * This replaces the old full-width drop panel. The Collector's job is to hold
 * images, so the place you put images belongs *among* them: the slot occupies
 * the first grid cell and each subsequent upload shifts the images along, which
 * makes "the collection" and "add to the collection" one continuous surface
 * instead of two stacked sections.
 *
 * It is sized exactly like a `RecordCard` image area (4:3) so it reads as a
 * tile, not a banner.
 */
export function GalleryUploadSlot({
  onUploaded,
  disabled = false,
}: GalleryUploadSlotProps) {
  const [isDragging, setDragging] = useState(false);
  const upload = useImageUpload(onUploaded, disabled);
  const { isBlocked, isUploading, progress, error, message } = upload;

  // A prompt block dragged over the grid must not be treated as a file drop —
  // RecordCard owns that gesture, so this slot ignores it and lets it pass.
  function handleDragOver(event: DragEvent<HTMLDivElement>) {
    if (isBlocked || isPromptDrag(event)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
    setDragging(true);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    if (isBlocked || isPromptDrag(event)) return;
    event.preventDefault();
    event.stopPropagation();
    setDragging(false);
    void upload.acceptFiles(event.dataTransfer.files);
  }

  return (
    <div
      onDragOver={handleDragOver}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      className={cn(
        "group relative overflow-hidden rounded-xl border bg-navy-850/40 transition-colors duration-150 ease-swift",
        isDragging
          ? "border-accent-400 bg-accent-500/10 shadow-glow"
          : "border-dashed border-navy-600/70 hover:border-accent-500/60 hover:bg-navy-800/50",
        isBlocked && "cursor-not-allowed opacity-60"
      )}
    >
      <button
        type="button"
        disabled={isBlocked}
        onClick={upload.openPicker}
        aria-label="Add images to the collection"
        className={cn(
          "flex aspect-[4/3] w-full flex-col items-center justify-center gap-2 px-3 text-center",
          isBlocked ? "cursor-not-allowed" : "cursor-pointer"
        )}
      >
        <span
          className={cn(
            "grid h-10 w-10 place-items-center rounded-xl border transition-colors",
            isDragging
              ? "border-accent-400/50 bg-accent-500/20 text-accent-200"
              : "border-navy-700/60 bg-navy-800/70 text-navy-300"
          )}
        >
          {isUploading ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          ) : (
            <UploadCloud className="h-4 w-4" aria-hidden />
          )}
        </span>

        <span className="text-[11px] font-medium text-navy-100">
          {isUploading ? "Uploading…" : isDragging ? "Drop to add" : "Add images"}
        </span>

        {isUploading ? (
          <span className="w-full max-w-[10rem]">
            <ProgressBar value={progress} label="Upload progress" />
          </span>
        ) : (
          <span className="text-[10px] leading-relaxed text-navy-400">
            Drop JPEG/PNG or click to browse
          </span>
        )}
      </button>

      {/* The hidden input lives on the tile so the slot is self-contained. */}
      <input
        ref={upload.inputRef}
        type="file"
        accept="image/jpeg,image/png,.jpg,.jpeg,.png"
        multiple
        className="hidden"
        onChange={(event) => void upload.acceptFiles(event.target.files)}
      />

      {error ? (
        <p role="alert" className="px-2.5 pb-2 text-[10px] text-red-300">
          {error}
        </p>
      ) : message ? (
        <p role="status" className="px-2.5 pb-2 text-[10px] text-navy-300">
          {message}
        </p>
      ) : (
        <p className="flex items-center gap-1 px-2.5 pb-2 text-[10px] text-navy-500">
          <FileImage className="h-2.5 w-2.5 shrink-0" aria-hidden />
          PNG is converted to JPEG
        </p>
      )}
    </div>
  );
}

export default GalleryUploadSlot;
