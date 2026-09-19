import type { Metadata } from "next";

import GalleryView from "@/components/gallery/GalleryView";

export const metadata: Metadata = {
  title: "Gallery · Adobe Stock AI Image Studio",
  description: "Browse, filter, download, and manage staged Adobe Stock assets.",
};

export default function GalleryPage() {
  return (
    <main className="min-h-screen px-6 py-8 text-zinc-100">
      <div className="mx-auto max-w-7xl space-y-6">
        <header>
          <h1 className="text-2xl font-bold tracking-tight">Gallery</h1>
          <p className="text-sm text-zinc-500">
            Staged, upload-ready assets. Mark images as used, download them, or
            build a copy/paste metadata table.
          </p>
        </header>

        <GalleryView />
      </div>
    </main>
  );
}
