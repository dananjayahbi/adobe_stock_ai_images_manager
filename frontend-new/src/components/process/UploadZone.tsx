"use client";

import { useCallback, useRef, useState, type DragEvent } from "react";
import Button from "@/components/ui/Button";

interface UploadZoneProps {
  disabled?: boolean;
  onFiles: (files: File[]) => void;
  uploading?: boolean;
  progress?: number;
}

const ACCEPT = ".jpg,.jpeg,.png";

/**
 * Drag-and-drop upload zone.
 *
 * Handlers live on the outer div, not the inner button — drops aimed at a
 * <button> are unreliable across browsers. The hidden input is the accessible
 * fallback (keyboard + click).
 */
export default function UploadZone({
  disabled = false,
  onFiles,
  uploading = false,
  progress,
}: UploadZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const handleDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      setDragging(false);
      if (disabled) return;
      const files = Array.from(event.dataTransfer.files);
      if (files.length > 0) onFiles(files);
    },
    [disabled, onFiles]
  );

  return (
    <div
      onDragOver={(event) => {
        event.preventDefault();
        if (!disabled) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      className={`frame-card flex flex-col items-center justify-center px-6 py-10 text-center transition-colors ${
        dragging ? "border-brass-400 bg-brass-300/10" : ""
      } ${disabled ? "opacity-60" : ""}`}
    >
      <span aria-hidden="true" className="font-script text-4xl text-parchment-600">
        ✦
      </span>
      <p className="mt-2 font-display text-lg text-ink-800">
        {uploading ? "Uploading…" : "Drop images here"}
      </p>
      <p className="mt-1 text-sm text-ink-400">
        JPEG and PNG · one drop, many files
      </p>

      {uploading && (
        <div className="mt-4 w-full max-w-xs">
          <div className="h-2 overflow-hidden rounded-full border border-parchment-400 bg-parchment-200">
            <div
              className="h-full bg-brass-400 transition-[width] duration-300"
              style={{ width: `${progress ?? 0}%` }}
            />
          </div>
        </div>
      )}

      <div className="mt-4">
        <Button
          variant="secondary"
          size="sm"
          disabled={disabled || uploading}
          onClick={() => inputRef.current?.click()}
        >
          Choose files
        </Button>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          multiple
          hidden
          onChange={(event) => {
            const files = Array.from(event.target.files ?? []);
            if (files.length > 0) onFiles(files);
            event.target.value = ""; // allow re-picking the same file
          }}
        />
      </div>
    </div>
  );
}
