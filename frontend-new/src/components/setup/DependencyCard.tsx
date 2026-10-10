import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { formatSizeMb } from "@/lib/format";
import type { InstallGroup } from "@/lib/setup";

interface DependencyCardProps {
  group: InstallGroup;
  /** A server-side install is running — blocks every Install button. */
  running: boolean;
  /** Any install/cancel request is in flight — disables every Install button. */
  busy: boolean;
  /** Only this card's own request is in flight — shows its spinner. */
  loading: boolean;
  onInstall: () => void;
}

/**
 * One install group (torch, matting stack, ViTMatte weights): size, stamped
 * status chip, and an Install button that always explains why it is disabled.
 */
export default function DependencyCard({
  group,
  running,
  busy,
  loading,
  onInstall,
}: DependencyCardProps) {
  const disabledReason = group.installed
    ? "Already installed"
    : running
      ? "An install is already running"
      : null;

  return (
    <div className="frame-card px-5 py-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-display text-lg text-ink-800">{group.label}</h3>
          <p className="label-caps mt-0.5">{formatSizeMb(group.size_mb)}</p>
        </div>
        <div className="flex flex-wrap justify-end gap-1.5">
          {group.installed ? (
            <Badge tone="success">
              Installed{group.version ? ` ${group.version}` : ""}
            </Badge>
          ) : (
            <Badge>Not installed</Badge>
          )}
          {group.ready && <Badge tone="info">Ready</Badge>}
        </div>
      </div>

      <div className="mt-4 flex items-center gap-3">
        <Button
          variant="secondary"
          size="sm"
          type="button"
          disabled={group.installed || running || busy}
          loading={loading}
          onClick={onInstall}
        >
          Install
        </Button>
        {disabledReason && (
          <span className="font-stamp text-[10px] uppercase tracking-[0.14em] text-ink-400">
            {disabledReason}
          </span>
        )}
      </div>
    </div>
  );
}
