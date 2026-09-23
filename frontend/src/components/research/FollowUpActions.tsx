"use client";

import { ArrowRight, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import type { FollowUpAction } from "@/lib/research";

export interface FollowUpActionsProps {
  actions: FollowUpAction[];
  /** Sends the action's canned message. */
  onSelect: (action: FollowUpAction) => void;
  disabled?: boolean;
  className?: string;
}

/**
 * The two choices offered after a validity assessment.
 *
 * Rendered from the *backend's* action list, so the buttons and the agent's
 * instructions cannot disagree about what the operator is being asked. Pressing
 * one sends its `message` through the normal chat endpoint — a button press and a
 * typed sentence are the same operation, which is why there is no separate
 * "continue" endpoint that could drift from the chat path.
 */
export default function FollowUpActions({
  actions,
  onSelect,
  disabled = false,
  className,
}: FollowUpActionsProps) {
  if (actions.length === 0) return null;

  return (
    <div className={cn("flex flex-wrap gap-2", className)}>
      {actions.map((action) => {
        const isContinue = action.id === "continue";
        return (
          <Button
            key={action.id}
            size="sm"
            variant={isContinue ? "primary" : "secondary"}
            disabled={disabled}
            icon={
              isContinue ? (
                <ArrowRight className="h-3.5 w-3.5" aria-hidden />
              ) : (
                <RefreshCw className="h-3.5 w-3.5" aria-hidden />
              )
            }
            onClick={() => onSelect(action)}
          >
            {action.label}
          </Button>
        );
      })}
    </div>
  );
}
