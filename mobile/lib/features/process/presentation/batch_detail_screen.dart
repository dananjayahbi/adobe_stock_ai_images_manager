import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:lucide_flutter/lucide_flutter.dart';

import '../../../app/theme/tokens.dart';
import '../../../core/utils/app_exception.dart';
import '../../../core/utils/formatters.dart';
import '../../../core/widgets/connection_profile_banner.dart';
import '../../../core/widgets/empty_state.dart';
import '../../../core/widgets/error_view.dart';
import '../../../core/widgets/ghost_button.dart';
import '../../../core/widgets/label_caps.dart';
import '../../../core/widgets/live_dot.dart';
import '../../../core/widgets/primary_button.dart';
import '../../../core/widgets/progress_bar.dart';
import '../../../core/widgets/secondary_button.dart';
import '../../../core/widgets/skeleton_loader.dart';
import '../../../core/widgets/stamp_badge.dart';
import '../../../core/widgets/status_chip.dart';
import '../../../core/widgets/thumbnail.dart';
import '../../../core/widgets/toast_exception.dart';
import '../domain/batch.dart';
import '../domain/batch_step.dart';
import '../domain/process_repository.dart';
import 'batch_card.dart';
import 'batch_controller.dart';
import 'batch_events_controller.dart';
import 'step_timeline.dart';

/// `/process/:batchId` (05 §2.7.2): live batch detail — header with status
/// + transport indicator ([LiveDot] while SSE flows, `POLLING` chip while
/// the 2.5s fallback runs), job ProgressBar, [StepTimeline] fed by live
/// snapshots, results grid, and the Run/Stop/Save-as-profile actions.
/// `batchEventsProvider` snapshots override the initial `batchDetailProvider`
/// payload; when both fail (404 after a studio restart — 02 §16) a friendly
/// error offers the way back to `/process`.
///
/// Offline (05 §3): a Run/Stop [NetworkException] kicks a detail re-probe —
/// a failing probe keeps the stale payload and lights the offline note
/// that dims Run/Stop; a succeeding probe clears both.
class BatchDetailScreen extends ConsumerWidget {
  const BatchDetailScreen({super.key, required this.batchId});

  /// The batch id from the route.
  final String batchId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final AsyncValue<BatchDetail> detailAsync = ref.watch(
      batchDetailProvider(batchId),
    );
    final BatchEventsState events = ref.watch(batchEventsProvider(batchId));
    return Scaffold(
      appBar: AppBar(title: const Text('Batch')),
      body: Column(
        children: <Widget>[
          const ConnectionProfileBanner(),
          Expanded(child: _content(context, ref, detailAsync, events)),
        ],
      ),
    );
  }

  Widget _content(
    BuildContext context,
    WidgetRef ref,
    AsyncValue<BatchDetail> detailAsync,
    BatchEventsState events,
  ) {
    if (events.error != null) {
      return _failure(context, ref, message: events.error!, gone: events.gone);
    }
    final BatchDetail? detail = detailAsync.value;
    if (detail == null) {
      if (detailAsync.hasError) {
        final Object error = detailAsync.error!;
        return _failure(
          context,
          ref,
          message: processErrorText(error),
          gone: error is NotFoundException,
        );
      }
      return _skeletons();
    }
    final Batch? liveBatch = events.latest?.batch;
    final Batch batch = liveBatch ?? detail;
    final List<BatchRecord> records = liveBatch is BatchDetail
        ? liveBatch.records
        : detail.records;
    return RefreshIndicator(
      onRefresh: () async {
        ref.invalidate(batchDetailProvider(batchId));
        await ref.read(batchDetailProvider(batchId).future);
      },
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(AppSpacing.md),
        children: <Widget>[
          _header(
            context,
            ref,
            batch,
            events,
            offline: detailAsync.error is NetworkException,
          ),
          const SizedBox(height: AppSpacing.lg),
          const LabelCaps(text: 'Steps'),
          const SizedBox(height: AppSpacing.sm),
          _timeline(context, ref, batch),
          if (records.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.lg),
            LabelCaps(text: 'Results (${records.length})'),
            const SizedBox(height: AppSpacing.sm),
            _results(records),
          ],
        ],
      ),
    );
  }

  Widget _header(
    BuildContext context,
    WidgetRef ref,
    Batch batch,
    BatchEventsState events, {
    required bool offline,
  }) {
    final StampTone tone = BatchCard.toneFor(batch.status);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Expanded(
              child: Text(
                batch.name,
                style: Theme.of(context).textTheme.titleLarge,
              ),
            ),
            StampBadge(label: batch.status, tone: tone),
          ],
        ),
        const SizedBox(height: AppSpacing.sm),
        Wrap(
          spacing: AppSpacing.sm,
          runSpacing: AppSpacing.xs,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: <Widget>[
            LabelCaps(
              text: batch.mediaType == 'png' ? 'Transparent' : 'Raster',
            ),
            LabelCaps(text: '${batch.recordCount} images'),
            if (batch.createdAt != null)
              LabelCaps(text: formatDateTime(batch.createdAt!)),
            if (events.live) const LiveDot(),
            if (events.pollingFallback)
              const StatusChip(
                label: 'POLLING',
                icon: LucideIcons.refreshCw,
                tone: StatusTone.warning,
              ),
          ],
        ),
        if (batch.isRunning || batch.status == 'completed') ...<Widget>[
          const SizedBox(height: AppSpacing.sm),
          ProgressBar(value: batch.progress),
        ],
        if (batch.status == 'failed' && batch.error != null) ...<Widget>[
          const SizedBox(height: AppSpacing.sm),
          Text(
            batch.error!,
            style: Theme.of(context).textTheme.bodySmall
                ?.copyWith(color: AppColors.rust400),
          ),
        ],
        const SizedBox(height: AppSpacing.md),
        Wrap(
          spacing: AppSpacing.sm,
          runSpacing: AppSpacing.sm,
          children: <Widget>[
            if (offline)
              Row(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  const Icon(
                    LucideIcons.wifiOff,
                    size: 14,
                    color: AppColors.rust400,
                  ),
                  const SizedBox(width: AppSpacing.xs),
                  Text(
                    'Offline — actions disabled. Pull to refresh.',
                    style: Theme.of(context).textTheme.bodySmall
                        ?.copyWith(color: AppColors.rust400),
                  ),
                ],
              ),
            if (batch.status == 'draft' ||
                batch.status == 'failed' ||
                batch.status == 'cancelled')
              _offlineGuard(
                offline,
                PrimaryButton(
                  label: 'Run batch',
                  onPressed: () => _run(context, ref, batch),
                ),
              ),
            // Stop doubles as "leave the queue" for queued batches (M4:
            // cancel works on both states); Run stays reserved for
            // draft/failed/cancelled above — never while queued|running.
            if (batch.isActive)
              _offlineGuard(
                offline,
                SecondaryButton(
                  label: 'Stop',
                  onPressed: () => _cancel(context, ref, batch),
                ),
              ),
            if (batch.steps.isNotEmpty)
              GhostButton(
                label: 'Save as profile',
                onPressed: () => _saveAsProfile(context, ref, batch),
              ),
          ],
        ),
      ],
    );
  }

  /// Dim + inert wrapper mirroring review_action_bar's offline guard (05 §3).
  Widget _offlineGuard(bool offline, Widget child) => offline
      ? Opacity(opacity: 0.5, child: IgnorePointer(child: child))
      : child;

  Widget _timeline(BuildContext context, WidgetRef ref, Batch batch) {
    final StepCatalog? catalog = ref
        .watch(stepCatalogProvider(batch.mediaType))
        .value;
    return StepTimeline(
      steps: batch.steps,
      progress: batch.stepProgress,
      catalog: catalog,
    );
  }

  Widget _results(List<BatchRecord> records) => GridView.builder(
    shrinkWrap: true,
    physics: const NeverScrollableScrollPhysics(),
    gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
      crossAxisCount: 3,
      mainAxisSpacing: AppSpacing.sm,
      crossAxisSpacing: AppSpacing.sm,
    ),
    itemCount: records.length,
    itemBuilder: (BuildContext context, int index) {
      final BatchRecord record = records[index];
      final String path = record.thumbnailPath ?? record.filename;
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Expanded(child: Thumbnail(path: path)),
          Text(
            record.filename,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: Theme.of(context).textTheme.labelSmall
                ?.copyWith(color: AppColors.ink400),
          ),
        ],
      );
    },
  );

  Widget _failure(
    BuildContext context,
    WidgetRef ref, {
    required String message,
    required bool gone,
  }) {
    if (gone) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.xl),
          child: EmptyState(
            title: message,
            message: 'The studio may have restarted. Your batches are safe.',
            icon: LucideIcons.circleAlert,
            action: SecondaryButton(
              label: 'Back to batches',
              onPressed: () => context.go('/process'),
            ),
          ),
        ),
      );
    }
    return ErrorView(
      message: message,
      onRetry: () => ref.read(batchEventsProvider(batchId).notifier).retry(),
    );
  }

  Widget _skeletons() => ListView(
    padding: const EdgeInsets.all(AppSpacing.md),
    children: const <Widget>[
      SkeletonLoader(height: 72),
      SkeletonLoader(height: 140),
      SkeletonLoader(height: 140),
    ],
  );

  Future<void> _run(BuildContext context, WidgetRef ref, Batch batch) async {
    final bool? confirmed = await _confirm(
      context,
      title: 'Run batch?',
      body: '“${batch.name}” will process ${batch.recordCount} images.',
      action: 'Run',
    );
    if (confirmed != true) {
      return;
    }
    try {
      await ref.read(processRepositoryProvider).runBatch(batch.id);
      if (context.mounted) {
        showAppToast(context, 'Batch started', tone: ToastTone.success);
      }
    } catch (error) {
      if (context.mounted) {
        showAppToast(context, processErrorText(error), tone: ToastTone.error);
      }
    } finally {
      // Re-probe: failure keeps the stale payload + lights the offline note.
      if (context.mounted) ref.invalidate(batchDetailProvider(batch.id));
    }
  }

  Future<void> _cancel(BuildContext context, WidgetRef ref, Batch batch) async {
    final bool? confirmed = await _confirm(
      context,
      title: 'Stop batch?',
      body: 'Processing stops where it is; finished steps are kept.',
      action: 'Stop',
    );
    if (confirmed != true) {
      return;
    }
    try {
      await ref.read(processRepositoryProvider).cancelBatch(batch.id);
      if (context.mounted) {
        showAppToast(context, 'Batch stopped', tone: ToastTone.neutral);
      }
    } catch (error) {
      if (context.mounted) {
        showAppToast(context, processErrorText(error), tone: ToastTone.error);
      }
    } finally {
      if (context.mounted) ref.invalidate(batchDetailProvider(batch.id));
    }
  }

  /// Save-as-profile posts the batch's current steps (02 §6 `step-profiles`).
  Future<void> _saveAsProfile(
    BuildContext context,
    WidgetRef ref,
    Batch batch,
  ) async {
    final TextEditingController controller = TextEditingController(
      text: batch.name,
    );
    final String? name = await showDialog<String>(
      context: context,
      builder: (BuildContext dialogContext) => AlertDialog(
        title: const Text('Save as profile'),
        content: TextField(
          controller: controller,
          autofocus: true,
          decoration: const InputDecoration(labelText: 'Profile name'),
          onSubmitted: (String value) =>
              Navigator.of(dialogContext).pop(value.trim()),
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () =>
                Navigator.of(dialogContext).pop(controller.text.trim()),
            child: const Text('Save'),
          ),
        ],
      ),
    );
    controller.dispose();
    if (name == null || name.isEmpty || !context.mounted) {
      return;
    }
    try {
      await ref
          .read(processRepositoryProvider)
          .createProfile(
            name: name,
            mediaType: batch.mediaType,
            steps: batch.steps,
          );
      if (context.mounted) {
        showAppToast(context, 'Profile saved', tone: ToastTone.success);
      }
    } catch (error) {
      if (context.mounted) {
        showAppToast(context, processErrorText(error), tone: ToastTone.error);
      }
    }
  }

  Future<bool?> _confirm(
    BuildContext context, {
    required String title,
    required String body,
    required String action,
  }) => showDialog<bool>(
    context: context,
    builder: (BuildContext dialogContext) => AlertDialog(
      title: Text(title),
      content: Text(body),
      actions: <Widget>[
        TextButton(
          onPressed: () => Navigator.of(dialogContext).pop(false),
          child: const Text('Cancel'),
        ),
        TextButton(
          onPressed: () => Navigator.of(dialogContext).pop(true),
          child: Text(action),
        ),
      ],
    ),
  );
}
