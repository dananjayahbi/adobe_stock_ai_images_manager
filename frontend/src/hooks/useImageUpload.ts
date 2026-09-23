"use client";

import { useCallback, useRef, useState, type RefObject } from "react";

import { uploadImages } from "@/lib/api";

/** Extensions the Collector accepts. PNG is converted to JPEG on ingestion. */
const ACCEPTED_EXTENSIONS = /\.(jpe?g|png)$/i;
/** Subset the backend rewrites, used only to explain the outcome. */
const CONVERTED_EXTENSIONS = /\.png$/i;

export interface UseImageUploadResult {
  isUploading: boolean;
  /** 0-100 upload progress. */
  progress: number;
  /** Human-readable outcome of the last attempt. */
  message: string | null;
  error: string | null;
  /** Attach to the hidden `<input type="file">` the tile renders. */
  inputRef: RefObject<HTMLInputElement>;
  /** Opens the OS file picker. */
  openPicker: () => void;
  /** Upload a `FileList` from a drop or a file input. */
  acceptFiles: (files: FileList | null) => Promise<void>;
  /** True while a drop should be ignored. */
  isBlocked: boolean;
}

/**
 * Image upload behaviour for the Collector.
 *
 * Extracted from the old `StageUploader` so the drop zone can be a *slot in the
 * image grid* rather than a full-width panel: the markup shrank to a tile, but
 * the validation, progress and result messaging are identical and should not be
 * reimplemented per placement.
 *
 * @param onUploaded Called after a successful upload so the page can refresh.
 * @param disabled External lock (e.g. while a queue push is in flight).
 */
export function useImageUpload(
  onUploaded: (count: number) => void,
  disabled = false
): UseImageUploadResult {
  const [isUploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const openPicker = useCallback(() => {
    inputRef.current?.click();
  }, []);

  const acceptFiles = useCallback(
    async (fileList: FileList | null) => {
      if (!fileList || fileList.length === 0) return;

      const all = Array.from(fileList);
      // Match on the name as well as the MIME type: a drag from some file
      // managers reports an empty or generic type for a valid image.
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

  return {
    isUploading,
    progress,
    message,
    error,
    inputRef,
    openPicker,
    acceptFiles,
    isBlocked: disabled || isUploading,
  };
}

export default useImageUpload;
