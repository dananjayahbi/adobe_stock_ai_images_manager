"use client";

import { FileImage, Loader2, UploadCloud } from "lucide-react";
import { useCallback, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Panel } from "@/components/ui/Panel";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { uploadImages } from "@/lib/api";
import { cn } from "@/lib/cn";

export interface StageUploaderProps {
  /** Called after a successful upload so the page can refresh its records. */
  onUploaded: (count: number) => void;
  disabled?: boolean;
}

/** Extensions the Collector accepts. PNG is converted to JPEG on ingestion. */
const ACCEPTED_EXTENSIONS = /\.(jpe?g|png)$/i;
/** Subset that the backend rewrites, used only to explain the outcome. */
const CONVERTED_EXTENSIONS = /\.png$/i;

/**
 * Collector upload target.
 *
 * Uploading is the Collector's only action, so the target is a full-width panel
 * rather than a small drop box: it is the first thing the operator interacts
 * with and the panel is the largest hit area we can give them.
 *
 * PNG is accepted because most generative tools emit it; the backend converts
 * it to a quality-100 JPEG during ingestion, so the operator never has to
 * pre-convert anything by hand.
 */
export function StageUploader({ onUploaded, disabled = false }: StageUploaderProps) {
  const [isDragging, setDragging] = useState(false);
  const [isUploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFiles = useCallback(
    async (fileList: FileList | null) => {
      if (!fileList || fileList.length === 0) return;

      const all = Array.from(fileList);
      // Match on the name as well as the MIME type: a drag-and-drop from some
      // file managers reports an empty or generic type for a valid image.
      const accepted = all.filter(
        (file) =>
          file.type === "image/jpeg" ||
          file.type === "image/png" ||
          ACCEPTED_EXTENSIONS.test(file.name)
      );

      if (accepted.length === 0) {
        setError("Only JPEG and PNG files (.jpg / .jpeg / .png) are accepted.");
        return;
      }

      setError(null);
      setMessage(
        accepted.length < all.length
          ? `${all.length - accepted.length} unsupported file(s) were skipped.`
          : null
      );
      setUploading(true);
      setProgress(0);

      try {
        const response = await uploadImages(accepted, setProgress);
        const pngCount = accepted.filter((file) =>
          CONVERTED_EXTENSIONS.test(file.name)
        ).length;
        const conversionNote =
          pngCount > 0
            ? ` ${pngCount} PNG${pngCount === 1 ? " was" : "s were"} converted to JPEG.`
            : "";
        setMessage(
          `Uploaded ${response.count} image${response.count === 1 ? "" : "s"} to the Collector.${conversionNote}`
        );
        onUploaded(response.count);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Upload failed.");
      } finally {
        setUploading(false);
        setProgress(0);
        if (inputRef.current) inputRef.current.value = "";
      }
    },
    [onUploaded]
  );

  const isBlocked = disabled || isUploading;

  return (
    <Panel className="p-4">
      <div
        role="button"
        tabIndex={isBlocked ? -1 : 0}
        aria-disabled={isBlocked}
        onClick={() => !isBlocked && inputRef.current?.click()}
        onKeyDown={(event) => {
          if (isBlocked) return;
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            inputRef.current?.click();
          }
        }}
        onDragOver={(event) => {
          event.preventDefault();
          if (!isBlocked) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          if (!isBlocked) void handleFiles(event.dataTransfer.files);
        }}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border border-dashed px-6 py-10 text-center",
          "transition-colors duration-150 ease-swift",
          isDragging
            ? "border-accent-500 bg-accent-500/10"
            : "border-navy-600/70 bg-navy-850/40 hover:border-accent-500/60 hover:bg-navy-800/50",
          isBlocked && "cursor-not-allowed opacity-60"
        )}
      >
        <span
          className={cn(
            "grid h-12 w-12 place-items-center rounded-xl border transition-colors",
            isDragging
              ? "border-accent-400/50 bg-accent-500/20 text-accent-200"
              : "border-navy-700/60 bg-navy-800/70 text-navy-300"
          )}
        >
          {isUploading ? (
            <Loader2 className="h-5 w-5 animate-spin" aria-hidden />
          ) : (
            <UploadCloud className="h-5 w-5" aria-hidden />
          )}
        </span>

        <div>
          <p className="text-sm font-medium text-navy-50">
            {isUploading ? "Uploading…" : "Drop JPEGs or PNGs here, or click to browse"}
          </p>
          <p className="mt-1 text-xs text-navy-400">
            PNGs are converted to quality-100 JPEGs automatically, because Adobe
            Stock accepts JPEG only for photos.
          </p>
        </div>

        {isUploading ? (
          <div className="w-full max-w-md space-y-1.5">
            <ProgressBar value={progress} label="Upload progress" />
            <p className="text-xs tabular-nums text-navy-300">{progress}%</p>
          </div>
        ) : (
          <Button size="sm" variant="secondary" disabled={isBlocked} icon={<FileImage className="h-3.5 w-3.5" aria-hidden />}>
            Choose files
          </Button>
        )}
      </div>

      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,.jpg,.jpeg,.png"
        multiple
        className="hidden"
        onChange={(event) => void handleFiles(event.target.files)}
      />

      {error ? (
        <p role="alert" className="mt-3 text-xs text-red-300">
          {error}
        </p>
      ) : message ? (
        <p role="status" className="mt-3 text-xs text-navy-300">
          {message}
        </p>
      ) : null}
    </Panel>
  );
}

export default StageUploader;
