import type { Metadata } from "next";

import StageWorkspaceView from "@/components/stages/StageWorkspaceView";

export const metadata: Metadata = {
  title: "Stages · Adobe Stock AI Image Studio",
  description:
    "Drive images through OCR, upscale, refinement, compatibility, metadata, and publishing.",
};

export default function StagesPage() {
  return (
    <main className="min-h-screen px-6 py-8 text-zinc-100">
      <div className="mx-auto max-w-7xl space-y-6">
        <header>
          <h1 className="text-2xl font-bold tracking-tight">Pipeline Stages</h1>
          <p className="text-sm text-zinc-500">
            Seven stages from collection to upload-ready. Every stage runs as a
            batch over your selection, and images only advance when they meet
            Adobe Stock&apos;s acceptance bar.
          </p>
        </header>

        <StageWorkspaceView />
      </div>
    </main>
  );
}
