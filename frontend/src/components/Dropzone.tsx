"use client";

import { AlertCircle, Loader2, UploadCloud } from "lucide-react";
import { useCallback, useRef, useState } from "react";

import { uploadImages, type UploadResponse } from "@/lib/api";

interface DropzoneProps {
  onUploadComplete?: (response: UploadResponse) => void;
}

export default function Dropzone({ onUploadComplete }: DropzoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFiles = useCallback(
    async (fileList: FileList | null) => {
      if (!fileList || fileList.length === 0) return;

      const all = Array.from(fileList);
      const jpegs = all.filter(
        (file) =>
          file.type === "image/jpeg" || /\.jpe?g$/i.test(file.name)
      );

      if (jpegs.length === 0) {
        setError("Only JPEG files (.jpg / .jpeg) are accepted.");
        return;
      }

      setError(
        jpegs.length < all.length
          ? `${all.length - jpegs.length} non-JPEG file(s) were skipped.`
          : null
      );
      setIsUploading(true);
      setProgress(0);

      try {
        const response = await uploadImages(jpegs, setProgress);
        onUploadComplete?.(response);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Upload failed.");
      } finally {
        setIsUploading(false);
        setProgress(0);
        if (inputRef.current) inputRef.current.value = "";
      }
    },
    [onUploadComplete]
  );

  return (
    <div className="space-y-3">
      <div
        role="button"
        tabIndex={0}
        aria-label="Upload JPEG images"
        onClick={() => !isUploading && inputRef.current?.click()}
        onKeyDown={(event) => {
          if ((event.key === "Enter" || event.key === " ") && !isUploading) {
            inputRef.current?.click();
          }
        }}
        onDragEnter={(event) => {
          event.preventDefault();
          if (!isUploading) setIsDragging(true);
        }}
        onDragOver={(event) => {
          event.preventDefault();
          if (!isUploading) setIsDragging(true);
        }}
        onDragLeave={(event) => {
          event.preventDefault();
          setIsDragging(false);
        }}
        onDrop={(event) => {
          event.preventDefault();
          setIsDragging(false);
          if (!isUploading) void handleFiles(event.dataTransfer.files);
        }}
        className={`rounded-xl border-2 border-dashed p-12 text-center transition-colors ${
          isUploading
            ? "cursor-wait border-sky-500/60 bg-sky-500/5"
            : isDragging
              ? "cursor-copy border-sky-400 bg-sky-500/10"
              : "cursor-pointer border-zinc-700 hover:border-sky-500/70 hover:bg-zinc-900/60"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".jpg,.jpeg,image/jpeg"
          multiple
          className="hidden"
          onChange={(event) => void handleFiles(event.target.files)}
        />

        <div className="flex flex-col items-center gap-3">
          {isUploading ? (
            <Loader2 className="h-10 w-10 animate-spin text-sky-400" />
          ) : (
            <UploadCloud
              className={`h-10 w-10 ${isDragging ? "text-sky-400" : "text-zinc-500"}`}
            />
          )}

          <p className="text-lg text-zinc-200">
            {isUploading
              ? `Uploading… ${progress}%`
              : isDragging
                ? "Drop JPEG files to upload"
                : "Drag and drop images here, or click to browse"}
          </p>
          <p className="text-sm text-zinc-500">
            JPEG only · multiple files supported · max 50 per batch
          </p>

          {isUploading && (
            <div className="mt-1 h-1.5 w-64 overflow-hidden rounded-full bg-zinc-800">
              <div
                className="h-full rounded-full bg-sky-500 transition-all"
                style={{ width: `${progress}%` }}
              />
            </div>
          )}
        </div>
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}
    </div>
  );
}
