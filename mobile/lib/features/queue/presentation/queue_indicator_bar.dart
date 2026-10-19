import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_flutter/lucide_flutter.dart';

import '../../../app/theme/tokens.dart';
import '../domain/queue_item.dart';
import '../domain/queue_state.dart';
import 'queue_controller.dart';

/// One-line queue status for the shell indicator (exposed for tests):
///
/// `Queue · 3 waiting — running wire_loop.jpg` · `Queue · paused` ·
/// `Queue · waiting for next image` · `Queue · N waiting` (idle).
String queueStatusText(QueueState state) {
  final int waiting = state.waitingCount;
  switch (state.runner) {
    case QueueRunnerStatus.waiting:
      return 'Queue · waiting for next image';
    case QueueRunnerStatus.running:
      final QueueItem? current =
          state.currentId == null ? null : state.byId(state.currentId!);
      final String name = current?.filename ?? '';
      if (name.isEmpty) {
        return 'Queue · $waiting waiting';
      }
      return 'Queue · $waiting waiting — running $name';
    case QueueRunnerStatus.paused:
      return waiting > 0 ? 'Queue · $waiting waiting — paused' : 'Queue · paused';
    case QueueRunnerStatus.idle:
      return 'Queue · $waiting waiting';
  }
}

/// Slim status strip pinned **above** the shell's bottom nav (built into
/// [AppShell], R3): queue count + current status, a play/pause toggle and
/// a tap-through to the Queue tab.
///
/// Visibility contract (documented decision): shown whenever the deque is
/// non-empty **or** the runner is live (`running`/`waiting` — a `waiting`
/// runner must stay legible because approvals auto-pick up). A `paused`
/// runner hides only when its deque is also empty (nothing to resume).
/// Hidden otherwise, so an idle empty queue costs no chrome. Both touch
/// targets are ≥44 dp.
class QueueIndicatorBar extends ConsumerWidget {
  const QueueIndicatorBar({super.key, required this.onOpenQueue});

  /// Taps anywhere on the bar (outside the play/pause button) jump to the
  /// Queue tab through the shell.
  final VoidCallback onOpenQueue;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final QueueState state = ref.watch(queueProvider);
    if (!state.isVisible) {
      return const SizedBox.shrink();
    }
    final bool busy = state.runner == QueueRunnerStatus.running ||
        state.runner == QueueRunnerStatus.waiting;
    return DecoratedBox(
      decoration: const BoxDecoration(
        color: AppColors.parchment50,
        border: Border(top: BorderSide(color: AppColors.parchment400)),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onOpenQueue,
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 44),
            child: Padding(
              padding: const EdgeInsets.only(
                left: AppSpacing.xs,
                right: AppSpacing.md,
              ),
              child: Row(
                children: <Widget>[
                  IconButton(
                    tooltip: busy ? 'Pause queue' : 'Start queue',
                    onPressed: () {
                      final QueueController controller =
                          ref.read(queueProvider.notifier);
                      unawaited(
                        busy ? controller.pause() : controller.start(),
                      );
                    },
                    icon: Icon(
                      busy ? LucideIcons.pause : LucideIcons.play,
                      size: 18,
                      color: AppColors.brass400,
                    ),
                    constraints: const BoxConstraints(
                      minWidth: 44,
                      minHeight: 44,
                    ),
                  ),
                  const SizedBox(width: AppSpacing.xs),
                  Expanded(
                    child: Text(
                      queueStatusText(state),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: AppColors.ink800,
                            height: 1.3,
                          ),
                    ),
                  ),
                  const SizedBox(width: AppSpacing.xs),
                  const Icon(
                    LucideIcons.chevronRight,
                    size: 16,
                    color: AppColors.ink400,
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
