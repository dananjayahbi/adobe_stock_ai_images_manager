import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/lifecycle_observer.dart';
import '../../../app/theme/tokens.dart';
import '../../../core/widgets/connection_profile_banner.dart';
import '../../../core/widgets/empty_state.dart';
import '../../../core/widgets/error_view.dart';
import '../../../core/widgets/ghost_button.dart';
import '../../../core/widgets/label_caps.dart';
import '../../../core/widgets/primary_button.dart';
import '../../../core/widgets/skeleton_loader.dart';
import '../../../core/widgets/toast_exception.dart';
import '../domain/batch.dart';
import 'batch_card.dart';
import 'batch_controller.dart';

/// `/process` tab (05 §2.7.1): batches overview — list, create, resume.
///
/// States: skeleton rows while loading, [EmptyState] ("No batches yet"),
/// [ErrorView] (+ pull-to-refresh retry) on failure/offline. Tap opens
/// `/process/:batchId`, long-press deletes after a confirm dialog; the
/// AppBar's New batch pushes the picker (`/process/pick`) while a `Wizard`
/// ghost keeps the 3-step flow reachable.
///
/// List contract (M4): sections `ACTIVE` (running + queued, positions as
/// `#n`) / `DRAFTS` / `FINISHED` in [sortBatchesForDisplay] order; while
/// anything is active a 2 s timer refreshes the list (cancelled on
/// dispose).
class ProcessScreen extends ConsumerStatefulWidget {
  const ProcessScreen({super.key});

  @override
  ConsumerState<ProcessScreen> createState() => _ProcessScreenState();
}

class _ProcessScreenState extends ConsumerState<ProcessScreen> {
  Timer? _poll;

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final AsyncValue<BatchList> listAsync = ref.watch(batchListProvider);
    _syncPolling(listAsync.value);
    // Resume revalidation (03 §4): refresh the batch list on foreground.
    final ProviderContainer container = ProviderScope.containerOf(context);
    AppLifecycleHooks.registerFeatureInvalidator(
      'process',
      () => container.invalidate(batchListProvider),
    );
    return Scaffold(
      appBar: AppBar(
        title: const Text('Process'),
        actions: <Widget>[
          PrimaryButton(
            label: 'New batch',
            onPressed: () => context.push('/process/pick'),
          ),
          const SizedBox(width: AppSpacing.sm),
          GhostButton(
            label: 'Wizard',
            onPressed: () => context.push('/process/new'),
          ),
          const SizedBox(width: AppSpacing.md),
        ],
      ),
      body: Column(
        children: <Widget>[
          const ConnectionProfileBanner(),
          Expanded(child: _content(context, listAsync)),
        ],
      ),
    );
  }

  /// Light polling (M4): while any batch is running/queued, refresh every
  /// 2 s so progress and queue positions advance without a pull; the timer
  /// stops the moment nothing is active (and on dispose).
  void _syncPolling(BatchList? list) {
    final bool active =
        list?.items.any((Batch batch) => batch.isActive) ?? false;
    if (active && _poll == null) {
      _poll = Timer.periodic(const Duration(seconds: 2), (Timer timer) {
        unawaited(ref.read(batchListProvider.notifier).refresh());
      });
    } else if (!active && _poll != null) {
      _poll?.cancel();
      _poll = null;
    }
  }

  Widget _content(BuildContext context, AsyncValue<BatchList> listAsync) {
    if (listAsync.isLoading && !listAsync.hasValue) {
      return _skeletons(context);
    }
    final BatchList? list = listAsync.value;
    if (list == null) {
      return ErrorView(
        message: processErrorText(listAsync.error ?? Exception('unknown')),
        onRetry: () => ref.read(batchListProvider.notifier).refresh(),
      );
    }
    Future<void> refresh() => ref.read(batchListProvider.notifier).refresh();
    // Refresh failed but rows are still on screen: inline error over the
    // stale list, never a full-screen takeover (05 §3).
    final Object? inline = listAsync.hasError ? listAsync.error : null;
    if (list.items.isEmpty) {
      return RefreshIndicator(
        onRefresh: refresh,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          children: <Widget>[
            if (inline != null)
              ErrorView(message: processErrorText(inline), onRetry: refresh),
            const SizedBox(height: AppSpacing.xxl * 4),
            EmptyState(
              title: 'No batches yet',
              message: 'Create a pipeline batch to process images.',
              action: PrimaryButton(
                label: 'New batch',
                onPressed: () => context.push('/process/pick'),
              ),
            ),
          ],
        ),
      );
    }

    final List<Batch> sorted = sortBatchesForDisplay(list.items);
    final Map<String, int> positions = queuePositions(sorted);
    final List<Batch> active = sorted
        .where((Batch batch) => batch.isActive)
        .toList();
    final List<Batch> drafts = sorted
        .where((Batch batch) => batch.status == 'draft')
        .toList();
    final List<Batch> finished = sorted
        .where((Batch batch) => batch.isTerminal)
        .toList();

    final List<Widget> rows = <Widget>[];
    if (inline != null) {
      rows.add(ErrorView(message: processErrorText(inline), onRetry: refresh));
    }

    void addSection(String title, List<Batch> items) {
      if (items.isEmpty) {
        return;
      }
      rows.add(
        Padding(
          padding: const EdgeInsets.fromLTRB(
            0,
            AppSpacing.lg,
            0,
            AppSpacing.sm,
          ),
          child: LabelCaps(text: title),
        ),
      );
      for (final Batch batch in items) {
        rows.add(
          Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.sm),
            child: BatchCard(
              batch: batch,
              queuePosition: positions[batch.id],
              onTap: () => context.push('/process/${batch.id}'),
              onLongPress: () => _confirmDelete(context, batch),
            ),
          ),
        );
      }
    }

    addSection('Active', active);
    addSection('Drafts', drafts);
    addSection('Finished', finished);

    return RefreshIndicator(
      onRefresh: refresh,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.md,
          AppSpacing.xs,
          AppSpacing.md,
          AppSpacing.xxl,
        ),
        children: rows,
      ),
    );
  }

  Widget _skeletons(BuildContext context) => ListView.separated(
    padding: const EdgeInsets.all(AppSpacing.md),
    itemCount: 4,
    separatorBuilder: (_, _) => const SizedBox(height: AppSpacing.sm),
    itemBuilder: (_, _) => const SkeletonLoader(height: 96),
  );

  Future<void> _confirmDelete(BuildContext context, Batch batch) async {
    final bool? confirmed = await showDialog<bool>(
      context: context,
      builder: (BuildContext dialogContext) => AlertDialog(
        title: const Text('Delete batch?'),
        content: Text('“${batch.name}” and its results will be removed.'),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (confirmed != true) {
      return;
    }
    try {
      await ref.read(batchListProvider.notifier).delete(batch.id);
      if (context.mounted) {
        showAppToast(context, 'Batch deleted', tone: ToastTone.success);
      }
    } catch (error) {
      if (context.mounted) {
        showAppToast(context, processErrorText(error), tone: ToastTone.error);
      }
    }
  }
}
