import { notFound } from "next/navigation";

import CollectorPage from "@/components/stages/pages/CollectorPage";
import CompatibilityPage from "@/components/stages/pages/CompatibilityPage";
import GalleryStagePage from "@/components/stages/pages/GalleryStagePage";
import MetadataPage from "@/components/stages/pages/MetadataPage";
import OcrPage from "@/components/stages/pages/OcrPage";
import RefinePage from "@/components/stages/pages/RefinePage";
import UpscalePage from "@/components/stages/pages/UpscalePage";
import { ALL_STAGE_META } from "@/lib/stageMeta";

/** One route per stage; the slug is the single source of navigation truth. */
const PAGES: Record<string, () => JSX.Element> = {
  collector: CollectorPage,
  ocr: OcrPage,
  upscale: UpscalePage,
  refine: RefinePage,
  compatibility: CompatibilityPage,
  metadata: MetadataPage,
  gallery: GalleryStagePage,
};

export function generateStaticParams() {
  return ALL_STAGE_META.map((meta) => ({ stage: meta.slug }));
}

export function generateMetadata({ params }: { params: { stage: string } }) {
  const meta = ALL_STAGE_META.find((entry) => entry.slug === params.stage);
  if (!meta) return { title: "Not found" };
  return {
    title: `${meta.name} · Adobe Stock AI Image Studio`,
    description: meta.tagline,
  };
}

export default function StageRoute({ params }: { params: { stage: string } }) {
  const Page = PAGES[params.stage];
  if (!Page) notFound();
  return <Page />;
}
