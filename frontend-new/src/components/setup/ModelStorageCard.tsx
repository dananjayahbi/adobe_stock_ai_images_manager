import Card from "@/components/ui/Card";
import { formatBytes } from "@/lib/format";
import type { ModelStorage } from "@/lib/setup";

interface ModelStorageCardProps {
  models: ModelStorage;
}

/**
 * Where weights live on disk: total size, the two caches that make it up,
 * the env paths that point at them, and the one-line rule for sharing a
 * library between machines (copy the directory, not the downloads).
 */
export default function ModelStorageCard({ models }: ModelStorageCardProps) {
  const total = models.rembg_bytes + models.hf_bytes;
  const envRows: { label: string; value: string }[] = [
    { label: "U2NET_HOME", value: models.env.U2NET_HOME },
    { label: "REMBG_HOME", value: models.env.REMBG_HOME },
    { label: "HF_HOME", value: models.env.HF_HOME },
  ];

  return (
    <Card
      header={
        <div className="flex items-baseline justify-between gap-3">
          <div>
            <p className="label-caps">Model storage</p>
            <h2 className="mt-0.5 font-display text-xl text-ink-800">
              Weights on disk
            </h2>
          </div>
          <span className="font-stamp text-xs text-ink-400">
            {formatBytes(total)}
          </span>
        </div>
      }
    >
      <div className="space-y-4">
        <div>
          <p className="label-caps">models_dir</p>
          <p className="mt-0.5 break-all font-mono text-xs text-ink-600">
            {models.models_dir}
          </p>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-sm border border-parchment-400/70 px-3 py-2">
            <p className="label-caps">rembg cache</p>
            <p className="mt-0.5 font-stamp text-sm text-ink-800">
              {formatBytes(models.rembg_bytes)}
            </p>
          </div>
          <div className="rounded-sm border border-parchment-400/70 px-3 py-2">
            <p className="label-caps">Hugging Face cache</p>
            <p className="mt-0.5 font-stamp text-sm text-ink-800">
              {formatBytes(models.hf_bytes)}
            </p>
          </div>
        </div>

        <div className="divider-dashed pt-3">
          <p className="label-caps mb-2">Environment paths</p>
          <dl className="space-y-1">
            {envRows.map((row) => (
              <div
                key={row.label}
                className="flex flex-wrap items-baseline justify-between gap-x-3"
              >
                <dt className="font-stamp text-[11px] uppercase tracking-[0.14em] text-ink-400">
                  {row.label}
                </dt>
                <dd className="min-w-0 break-all font-mono text-xs text-ink-600">
                  {row.value}
                </dd>
              </div>
            ))}
          </dl>
        </div>

        <p className="text-sm text-ink-400">
          Copy <span className="font-mono text-xs text-ink-600">models_dir</span>{" "}
          to another machine and it shares every weight — rembg and Hugging
          Face caches both live under it, so no re-downloads.
        </p>
      </div>
    </Card>
  );
}
