import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/theme/tokens.dart';
import '../../../core/widgets/primary_button.dart';
import '../../../core/widgets/secondary_button.dart';
import '../domain/queue_item.dart';
import '../domain/queue_state.dart';
import 'queue_controller.dart';

/// Bottom control area of the Queue screen (R3): a running/idle banner
/// over the **Start**/**Pause** button. Parked as the screen's inner
/// `bottomNavigationBar`, so it floats directly above the shell's tab bar
/// (never covering it — same nesting pattern as the gallery toolbar).
class QueueControls extends ConsumerWidget {
  const QueueControls({super.key});

  /// Banner copy per runner state — exposed through the widget tree via
  /// [queueStatusBanner] for the screen tests.
  static String bannerFor(QueueState state) {
    switch (state.runner) {
      case QueueRunnerStatus.running:
        return 'Running — promoting one image at a time.';
      case QueueRunnerStatus.waiting:
        return 'Waiting for next image — new approvals join the queue.';
      case QueueRunnerStatus.paused:
        return state.waitingCount > 0
            ? 'Paused · ${state.waitingCount} waiting. Press Start to resume.'
            : 'Paused. Press Start to resume.';
      case QueueRunnerStatus.idle:
        return 'Idle — press Start to begin.';
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final QueueState state = ref.watch(queueProvider);
    final bool busy = state.runner == QueueRunnerStatus.running ||
        state.runner == QueueRunnerStatus.waiting;
    return DecoratedBox(
      decoration: const BoxDecoration(
        color: AppColors.parchment50,
        border: Border(top: BorderSide(color: AppColors.parchment400)),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.lg,
          AppSpacing.md,
          AppSpacing.lg,
          AppSpacing.md,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Row(
              children: <Widget>[
                Expanded(
                  child: Text(
                    bannerFor(state),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: AppColors.ink600,
                          height: 1.35,
                        ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.sm),
            if (busy)
              SecondaryButton(
                label: 'Pause',
                expanded: true,
                onPressed: () {
                  unawaited(ref.read(queueProvider.notifier).pause());
                },
              )
            else
              PrimaryButton(
                label: 'Start',
                expanded: true,
                onPressed: () {
                  unawaited(ref.read(queueProvider.notifier).start());
                },
              ),
          ],
        ),
      ),
    );
  }
}
