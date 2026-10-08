"use client";

import { useState } from "react";
import Link from "next/link";
import NewBatchModal from "@/components/batch/NewBatchModal";
import LatestGrid from "@/components/home/LatestGrid";
import Button from "@/components/ui/Button";

/**
 * Home: hero + New batch / Gallery actions + the latest processed images.
 * The wizard is page-owned; the grid only needs the opener callback.
 */
export default function HomePage() {
  const [wizardOpen, setWizardOpen] = useState(false);

  return (
    <div className="space-y-10">
      <section className="relative overflow-hidden frame-card px-6 py-10 text-center sm:py-14">
        <p className="label-caps">A local pipeline for Adobe Stock</p>
        <h1 className="mt-3 font-display text-4xl leading-tight text-ink-800 sm:text-5xl">
          Process images in{" "}
          <span className="font-script text-oxblood-500">batches</span>
        </h1>
        <p className="mx-auto mt-4 max-w-xl text-lg leading-relaxed text-ink-400">
          Choose raster photos or transparent cut-outs, pick exactly the steps
          you need, and run the whole pipeline in one go.
        </p>
        <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
          <Button size="lg" onClick={() => setWizardOpen(true)}>
            New batch
          </Button>
          <Link href="/gallery">
            <Button variant="secondary" size="lg">
              Open gallery
            </Button>
          </Link>
        </div>

        {/* Corner flourishes, like an engraved certificate. */}
        <span
          aria-hidden="true"
          className="pointer-events-none absolute left-3 top-3 font-script text-3xl text-brass-400/50"
        >
          ✦
        </span>
        <span
          aria-hidden="true"
          className="pointer-events-none absolute bottom-3 right-3 font-script text-3xl text-brass-400/50"
        >
          ✦
        </span>
      </section>

      <LatestGrid onNewBatch={() => setWizardOpen(true)} />

      <NewBatchModal open={wizardOpen} onClose={() => setWizardOpen(false)} />
    </div>
  );
}
