import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/utils/app_exception.dart';
import '../../../core/utils/ui_message.dart';
import '../../platforms/presentation/platforms_controller.dart';
import '../domain/batch.dart';
import '../domain/batch_step.dart';
import '../domain/process_repository.dart';

/// Gallery failures must surface immediately (05 states) — never sit behind
/// riverpod's default exponential auto-retry. Manual retry / pull-to-refresh
/// is the way back (same rule as `galleryControllerProvider`).
Duration? _noRetry(int retryCount, Object error) => null;

/// `GET platformPath(id, 'batches?limit=50')` → the `/process` list.
final batchListProvider = AsyncNotifierProvider<BatchListController, BatchList>(
  BatchListController.new,
  retry: _noRetry,
);

/// List state for `/process` (05 §2.7.1): skeleton / empty / error / data +
/// pull-to-refresh. Platform switch rebuilds through `activePlatformIdProvider`
/// (03 §3.5).
class BatchListController extends AsyncNotifier<BatchList> {
  @override
  Future<BatchList> build() {
    ref.watch(activePlatformIdProvider);
    return ref.watch(processRepositoryProvider).fetchBatches();
  }

  /// Pull-to-refresh: keeps the current rows on screen while the reload runs
  /// (RefreshIndicator owns the spinner), landing in error on failure.
  Future<void> refresh() async {
    state = await AsyncValue.guard(
      () => ref.read(processRepositoryProvider).fetchBatches(),
    );
  }

  /// Long-press → confirm → remove a batch (409 while running bubbles as
  /// [AppException]); the list reloads so the row disappears.
  Future<void> delete(String batchId) async {
    await ref.read(processRepositoryProvider).deleteBatch(batchId);
    await refresh();
  }
}

/// `GET platformPath(id, 'batches/{batchId}')` — initial payload for
/// `/process/:batchId` (records for the results grid; SSE frames carry no
/// `records`, so this is the only source of them for a live batch).
final batchDetailProvider = FutureProvider.autoDispose
    .family<BatchDetail, String>(
      (Ref ref, String batchId) =>
          ref.watch(processRepositoryProvider).fetchBatchDetail(batchId),
      retry: _noRetry,
    );

/// `GET platformPath(id, 'batches/steps?media_type=…')` — step catalog for
/// the New batch wizard's custom-pipeline step (keys + labels + defaults).
final stepCatalogProvider = FutureProvider.autoDispose
    .family<StepCatalog, String>(
      (Ref ref, String mediaType) => ref
          .watch(processRepositoryProvider)
          .fetchStepCatalog(mediaType: mediaType),
      retry: _noRetry,
    );

/// `GET platformPath(id, 'step-profiles?media_type=…')` — saved profiles for
/// the wizard's profile step (02 §6; wired in backend `step_profiles.py`).
final stepProfilesProvider = FutureProvider.autoDispose
    .family<List<StepProfile>, String>(
      (Ref ref, String mediaType) => ref
          .watch(processRepositoryProvider)
          .fetchProfiles(mediaType: mediaType),
      retry: _noRetry,
    );

/// Human line for a thrown object (same rule as gallery's `errorText`).
String processErrorText(Object error) =>
    error is AppException ? uiMessageFor(error) : 'Something went wrong.';

/// Action-flavored line for picker/queue failures: the backend `detail`
/// verbatim when the error interceptor captured one (403 escape, 409
/// conflicts, 400 validation), else the shared human copy above.
String actionErrorText(Object error) {
  if (error is AppException) {
    final bool detailBearing =
        error is ServerException ||
        error is ValidationException ||
        error is NotFoundException;
    final String? detail = error.message;
    if (detailBearing && detail != null && detail.isNotEmpty) {
      return detail;
    }
  }
  return processErrorText(error);
}

/// Contract order for the `/process` list (M4): running → queued (by
/// `queued_at`, oldest first) → draft → terminal (updated_at desc). Ties
/// inside the non-queue ranks fall back to updated-at desc, newest first.
List<Batch> sortBatchesForDisplay(Iterable<Batch> items) {
  final List<Batch> sorted = items.toList();
  sorted.sort((Batch a, Batch b) {
    final int byRank = _statusRank(a.status).compareTo(_statusRank(b.status));
    if (byRank != 0) {
      return byRank;
    }
    if (a.status == 'queued') {
      final DateTime at =
          a.queuedAt ?? a.createdAt ?? DateTime.fromMillisecondsSinceEpoch(0);
      final DateTime bt =
          b.queuedAt ?? b.createdAt ?? DateTime.fromMillisecondsSinceEpoch(0);
      final int byQueue = at.compareTo(bt);
      if (byQueue != 0) {
        return byQueue;
      }
    }
    final DateTime au =
        a.updatedAt ?? a.createdAt ?? DateTime.fromMillisecondsSinceEpoch(0);
    final DateTime bu =
        b.updatedAt ?? b.createdAt ?? DateTime.fromMillisecondsSinceEpoch(0);
    return bu.compareTo(au);
  });
  return sorted;
}

int _statusRank(String status) => switch (status) {
  'running' => 0,
  'queued' => 1,
  'draft' => 2,
  _ => 3, // terminal: completed | failed | cancelled
};

/// Queue positions for a list already in [sortBatchesForDisplay] order —
/// 1-based index among queued (contract: index + 1), keyed by batch id.
Map<String, int> queuePositions(Iterable<Batch> items) {
  final Map<String, int> positions = <String, int>{};
  int next = 1;
  for (final Batch batch in items) {
    if (batch.status == 'queued') {
      positions[batch.id] = next;
      next += 1;
    }
  }
  return positions;
}
