interface ProgressBarProps {
  /** 0-100. Null renders an indeterminate barber-pole. */
  value: number | null;
  tone?: "brass" | "oxblood" | "olive";
  label?: string;
}

const TONES = {
  brass: "bg-brass-400",
  oxblood: "bg-oxblood-500",
  olive: "bg-olive-500",
};

/** Thin ruled progress bar, like an old ledger's fill line. */
export default function ProgressBar({
  value,
  tone = "brass",
  label,
}: ProgressBarProps) {
  const clamped = value === null ? null : Math.max(0, Math.min(100, value));
  return (
    <div className="w-full">
      {label && (
        <div className="mb-1 flex items-center justify-between">
          <span className="label-caps">{label}</span>
          {clamped !== null && (
            <span className="font-stamp text-[11px] text-ink-400">
              {Math.round(clamped)}%
            </span>
          )}
        </div>
      )}
      <div className="h-2 w-full overflow-hidden rounded-full border border-parchment-400 bg-parchment-200">
        {clamped === null ? (
          <div className="h-full w-full animate-pulse bg-brass-400/60" />
        ) : (
          <div
            className={`h-full rounded-full transition-[width] duration-500 ${TONES[tone]}`}
            style={{ width: `${clamped}%` }}
          />
        )}
      </div>
    </div>
  );
}
