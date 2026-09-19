import type { Metadata } from "next";
import { Images } from "lucide-react";

import GalleryView from "@/components/gallery/GalleryView";
import { PageHeader } from "@/components/ui/PageHeader";
import { PageShell } from "@/components/shell/PageShell";

export const metadata: Metadata = {
  title: "Gallery · Adobe Stock AI Image Studio",
  description: "Browse, filter, download, and manage staged Adobe Stock assets.",
};

export default function GalleryPage() {
  return (
    <PageShell>
      <PageHeader
        title="Gallery"
        tagline="Staged, upload-ready assets. Mark images as used, download them, or build a copy/paste metadata table."
        icon={<Images className="h-5 w-5" aria-hidden />}
      />
      <GalleryView />
    </PageShell>
  );
}
