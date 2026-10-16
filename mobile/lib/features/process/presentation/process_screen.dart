import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/lifecycle_observer.dart';
import '../../../app/theme/tokens.dart';
import '../../../core/widgets/connection_profile_banner.dart';
import '../../../core/widgets/empty_state.dart';
import '../../../core/widgets/error_view.dart';
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
/// `/process/:batchId`, long-press deletes after a confirm dialog, and the
/// AppBar's New batch button pushes `/process/new`.
class ProcessScreen extends ConsumerWidget {
  const ProcessScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final AsyncValue<BatchList> listAsync = ref.watch(batchListProvider);
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
            onPressed: () => context.push('/process/new'),
          ),
          const SizedBox(width: AppSpacing.md),
        ],
      ),
      body: Column(
        children: <Widget>[
          const ConnectionProfileBanner(),
          Expanded(child: _content(context, ref, listAsync)),
        ],
      ),
    );
  }

  Widget _content(
    BuildContext context,
    WidgetRef ref,
    AsyncValue<BatchList> listAsync,
  ) {
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
              ErrorView(
                message: processErrorText(inline),
                onRetry: refresh,
              ),
            const SizedBox(height: AppSpacing.xxl * 4),
            EmptyState(
              title: 'No batches yet',
              message: 'Create a pipeline batch to process images.',
              action: PrimaryButton(
                label: 'New batch',
                onPressed: () => context.push('/process/new'),
              ),
            ),
          ],
        ),
      );
    }
    return RefreshIndicator(
      onRefresh: refresh,
      child: ListView.separated(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(AppSpacing.md),
        itemCount: list.items.length + (inline != null ? 1 : 0),
        separatorBuilder: (_, _) => const SizedBox(height: AppSpacing.sm),
        itemBuilder: (BuildContext context, int index) {
          if (inline != null) {
            if (index == 0) {
              return ErrorView(
                message: processErrorText(inline),
                onRetry: refresh,
              );
            }
            index -= 1;
          }
          final Batch batch = list.items[index];
          return BatchCard(
            batch: batch,
            onTap: () => context.push('/process/${batch.id}'),
            onLongPress: () => _confirmDelete(context, ref, batch),
          );
        },
      ),
    );
  }

  Widget _skeletons(BuildContext context) => ListView.separated(
        padding: const EdgeInsets.all(AppSpacing.md),
        itemCount: 4,
        separatorBuilder: (_, _) => const SizedBox(height: AppSpacing.sm),
        itemBuilder: (_, _) => const SkeletonLoader(height: 96),
      );

  Future<void> _confirmDelete(
    BuildContext context,
    WidgetRef ref,
    Batch batch,
  ) async {
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
