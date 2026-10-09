"use client";

import Button from "@/components/ui/Button";

interface SelectionModeToggleProps {
  active: boolean;
  onToggle: () => void;
}

/**
 * Switches the gallery between *browse* (click opens the preview) and
 * *select* (click ticks a tile, dragging paints a rubber band) — the desktop
 * convention for picking many files without ticking each checkbox by hand.
 */
export default function SelectionModeToggle({ active, onToggle }: SelectionModeToggleProps) {
  return (
    <Button
      variant={active ? "primary" : "secondary"}
      size="sm"
      type="button"
      aria-pressed={active}
      onClick={onToggle}
      title="Click images to tick them, or drag a box to select many at once"
    >
      {active ? "✓ Selecting" : "☐ Select"}
    </Button>
  );
}
