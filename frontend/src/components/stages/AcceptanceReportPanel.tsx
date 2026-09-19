"use client";

import { AlertTriangle, Info } from "lucide-react";

import {
  formatScore,
  scoreTone,
  type AcceptanceReport,
} from "@/lib/stages";
import { isAutoFixable } from "@/lib/acceptanceIssues";

interface AcceptanceReportPanelProps {
  report: AcceptanceReport;
  /** Ordered remediation advice from Stage 5, when available. */
  remediation?: string[];
}

const SEVERITY_STYLES: Record<string, string> = {
  critical: "border-red-500/40 bg-red-500/10 text-red-200",
  major: "border-amber-500/40 bg-amber-500/10 text-amber-200",
  minor: "border-navy-600/50 bg-navy-700/20 text-navy-200",
};

const TONE_BAR: Record<ReturnType<typeof scoreTone>, string> = {
  good: "bg-emerald-500",
  warn: "bg-amber-500",
  bad: "bg-red-500",
  none: "bg-navy-600",
};

/**
 * Explains *why* an image scored what it did.
 *
 * A bare percentage is not actionable, so this breaks the score into its five
 * weighted components and lists every detected issue with its severity. The
 * component bars make it obvious which dimension is dragging the total down.
 */
export default function AcceptanceReportPanel({
  report,
  remediation,
}: AcceptanceReportPanelProps) {
  const tone = scoreTone(report.score);
  const components = Object.values(report.sub_scores);

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-navy-800 bg-navy-900/60 p-4">
        <div className="flex items-end justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-wide text-navy-400">
              Acceptance score
            </p>
            <p className="text-3xl font-bold tabular-nums text-navy-50">
              {formatScore(report.score)}
            </p>
          </div>
          <div className="text-right text-xs text-navy-400">
            <p>
              Threshold{" "}
              <span className="font-semibold text-navy-200">
                {formatScore(report.threshold)}
              </span>
            </p>
            <p>
              {report.semantic_included
                ? "Includes AI semantic review"
                : "Pixel analysis only"}
            </p>
          </div>
        </div>

        <div className="mt-3 h-2 overflow-hidden rounded-full bg-navy-800">
          <div
            className={`h-full rounded-full ${TONE_BAR[tone]}`}
            style={{ width: `${Math.min(report.score * 100, 100)}%` }}
          />
        </div>

        <p
          className={`mt-2 text-sm font-medium ${
            report.passed ? "text-emerald-300" : "text-amber-300"
          }`}
        >
          {report.passed
            ? "Clears the Adobe Stock acceptance threshold."
            : "Below threshold - see the issues below."}
        </p>
      </div>

      {/* Weighted component breakdown */}
      <div className="space-y-2">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-navy-400">
          Score components
        </h4>
        {components.map((component) => {
          const componentTone = scoreTone(component.score);
          return (
            <div key={component.key}>
              <div className="mb-1 flex items-center justify-between text-xs">
                <span className="text-navy-300">
                  {component.label}
                  <span className="ml-1.5 text-navy-600">
                    {Math.round(component.weight * 100)}%
                  </span>
                </span>
                <span className="tabular-nums text-navy-200">
                  {formatScore(component.score)}
                </span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-navy-800">
                <div
                  className={`h-full rounded-full ${TONE_BAR[componentTone]}`}
                  style={{ width: `${Math.min(component.score * 100, 100)}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>

      {/* Detected issues */}
      {report.issues.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-navy-400">
            Detected issues ({report.issues.length})
          </h4>
          <ul className="space-y-1.5">
            {report.issues.map((issue, index) => (
              <li
                key={`${issue.code}-${index}`}
                className={`rounded border px-2.5 py-1.5 text-xs ${
                  SEVERITY_STYLES[issue.severity] ?? SEVERITY_STYLES.minor
                }`}
              >
                <div className="flex items-center gap-1.5">
                  <AlertTriangle className="h-3 w-3 shrink-0" />
                  <span className="font-semibold uppercase tracking-wide">
                    {issue.severity}
                  </span>
                  <span className="font-mono text-[10px] opacity-70">
                    {issue.code}
                  </span>
                  {/*
                   * Derived from the code, not from the report's cached
                   * `refinable` flag: a report persisted before the engine
                   * gained a capability would otherwise hide the badge for an
                   * issue the pipeline can now fix.
                   */}
                  {isAutoFixable(issue.code) && (
                    <span
                      title="The Auto-fix button below can correct this automatically."
                      className="ml-auto rounded bg-violet-500/20 px-1.5 py-0.5 text-[10px] text-violet-200"
                    >
                      auto-fixable
                    </span>
                  )}
                </div>
                <p className="mt-1 opacity-90">{issue.detail}</p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Stage 5 remediation advice */}
      {remediation && remediation.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-navy-400">
            What to do
          </h4>
          <ul className="space-y-1.5">
            {remediation.map((hint, index) => (
              <li
                key={index}
                className="flex items-start gap-2 rounded border border-accent-500/30 bg-accent-500/10 px-2.5 py-1.5 text-xs text-accent-100"
              >
                <Info className="mt-0.5 h-3 w-3 shrink-0" />
                <span>{hint}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
