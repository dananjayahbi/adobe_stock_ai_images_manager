import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_flutter/lucide_flutter.dart';

import '../../../app/theme/tokens.dart';
import '../../../core/widgets/empty_state.dart';
import '../../../core/widgets/label_caps.dart';
import '../../../core/widgets/status_chip.dart';
import '../domain/queue_item.dart';
import '../domain/queue_state.dart';
import 'queue_controls.dart';
import 'queue_controller.dart';

/// Queue tab (R3): every queued/done/failed promote item with per-item
/// error text, plus the Start/Pause control area. Replaces the Process
/// tab in the shell — batches remain reachable at `/process/new` and
/// `/process/:batchId`.
class QueueScreen extends ConsumerWidget {
  const QueueScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final QueueState state = ref.watch(queueProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Queue')),
      body: Column(
        children: <Widget>[
          Padding(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.lg,
              AppSpacing.sm,
              AppSpacing.lg,
              AppSpacing.xs,
            ),
            child: Row(
              children: <Widget>[
                const LabelCaps(text: 'READINESS QUEUE'),
                const Spacer(),
                Text(
                  '${state.waitingCount} waiting',
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: AppColors.ink600,
                      ),
                ),
              ],
            ),
          ),
          Expanded(
            child: state.isEmpty
                ? const EmptyState(
                    icon: LucideIcons.listChecks,
                    title: 'Nothing queued',
                    message: 'Approving an image (or moving it to Ready to '
                        'publish) queues it here for its promote check pass.',
                  )
                : ListView.separated(
                    padding: const EdgeInsets.only(bottom: AppSpacing.md),
                    itemCount: state.items.length,
                    separatorBuilder: (BuildContext context, int index) =>
                        const Divider(
                      height: 1,
                      color: AppColors.parchment400,
                    ),
                    itemBuilder: (BuildContext context, int index) =>
                        _QueueItemTile(item: state.items[index]),
                  ),
          ),
        ],
      ),
      bottomNavigationBar: const QueueControls(),
    );
  }
}

/// One deque row: state chip, filename (or raw id), failure reason and —
/// only when legal — Retry (failed) / Remove (everything but running).
class _QueueItemTile extends ConsumerWidget {
  const _QueueItemTile({required this.item});

  final QueueItem item;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final (String label, IconData icon, StatusTone tone) = _presentation(
      item.status,
    );
    final bool failed = item.status == QueueItemStatus.failed;
    final bool removable = item.status != QueueItemStatus.running;
    return Padding(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.lg,
        vertical: AppSpacing.sm,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          StatusChip(label: label, icon: icon, tone: tone, dense: true),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  item.filename.isEmpty ? item.recordId : item.filename,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: AppColors.ink800,
                      ),
                ),
                if (failed && (item.error?.isNotEmpty ?? false)) ...<Widget>[
                  const SizedBox(height: 2),
                  Text(
                    item.error!,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: AppColors.rust400,
                          height: 1.3,
                        ),
                  ),
                ],
              ],
            ),
          ),
          if (failed)
            IconButton(
              tooltip: 'Retry',
              constraints: const BoxConstraints(
                minWidth: 44,
                minHeight: 44,
              ),
              onPressed: () {
                ref.read(queueProvider.notifier).retry(item.recordId);
              },
              icon: const Icon(LucideIcons.rotateCcw, size: 18),
            ),
          if (removable)
            IconButton(
              tooltip: 'Remove from queue',
              constraints: const BoxConstraints(
                minWidth: 44,
                minHeight: 44,
              ),
              onPressed: () {
                ref.read(queueProvider.notifier).remove(item.recordId);
              },
              icon: const Icon(LucideIcons.x, size: 18),
            ),
        ],
      ),
    );
  }
}

(String, IconData, StatusTone) _presentation(QueueItemStatus status) =>
    switch (status) {
      QueueItemStatus.waiting => (
          'Waiting',
          LucideIcons.clock3,
          StatusTone.neutral,
        ),
      QueueItemStatus.running => (
          'Running',
          LucideIcons.refreshCw,
          StatusTone.accent,
        ),
      QueueItemStatus.done => (
          'Done',
          LucideIcons.circleCheck,
          StatusTone.success,
        ),
      QueueItemStatus.failed => (
          'Failed',
          LucideIcons.triangleAlert,
          StatusTone.failure,
        ),
    };
