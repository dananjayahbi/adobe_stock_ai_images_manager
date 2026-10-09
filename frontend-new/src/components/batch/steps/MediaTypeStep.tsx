"use client";

import type { MediaType } from "@/lib/types";

interface Props {
  value: MediaType | null;
  onSelect: (type: MediaType) => void;
}

const OPTIONS: {
  type: MediaType;
  title: string;
  glyph: string;
  body: string;
}[] = [
  {
    type: "raster",
    title: "Raster photos",
    glyph: "◨",
    body: "JPEG-ready photographs. Runs the photo pipeline: OCR, upscale, refine, acceptance QC, metadata.",
  },
  {
    type: "png",
    title: "Transparent PNGs",
    glyph: "◈",
    body: "Isolated objects on transparency. Adds background removal with an edge-quality check, and keeps alpha end to end.",
  },
];

/** Wizard step 1 — pick what kind of batch this is. */
export default function MediaTypeStep({ value, onSelect }: Props) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {OPTIONS.map((option) => {
        const active = value === option.type;
        return (
          <button
            key={option.type}
            type="button"
            onClick={() => onSelect(option.type)}
            aria-pressed={active}
            className={`frame-card group px-5 py-6 text-left transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-brass-400 ${
              active
                ? "-translate-y-0.5 border-oxblood-500 ring-1 ring-oxblood-500"
                : "hover:-translate-y-0.5 hover:border-parchment-500"
            }`}
          >
            <div className="mb-3 flex items-center justify-between">
              <span
                className={`font-script text-4xl leading-none ${active ? "text-oxblood-400" : "text-parchment-600"}`}
              >
                {option.glyph}
              </span>
              {active && <span className="stamp">Selected</span>}
            </div>
            <h3 className="font-display text-lg text-ink-800">{option.title}</h3>
            <p className="mt-1.5 text-sm leading-relaxed text-ink-400">
              {option.body}
            </p>
          </button>
        );
      })}
    </div>
  );
}
