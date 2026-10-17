import ProcessBoard from "@/components/process/ProcessBoard";

/**
 * Processes: the serial run queue at a glance — what is running or waiting,
 * what is drafted, and what has finished — with every row opening back into
 * the batch page. Server component shell; all polling lives in the board's
 * client hook (no search params, so no Suspense boundary needed).
 */
export default function ProcessesPage() {
  return (
    <div className="space-y-6">
      {/* Header: label + title, then the reference's layered rule lines. */}
      <div>
        <p className="label-caps">The queue</p>
        <h1 className="mt-1 font-display text-3xl text-ink-800">Processes</h1>
        <div className="mt-3 h-px bg-brass-400/50" />
        <div className="mt-[2px] h-px bg-parchment-400" />
      </div>

      <ProcessBoard />
    </div>
  );
}
