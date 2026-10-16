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
final batchListProvider =
    AsyncNotifierProvider<BatchListController, BatchList>(
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
final batchDetailProvider = FutureProvider.autoDispose.family<BatchDetail, String>(
  (Ref ref, String batchId) =>
      ref.watch(processRepositoryProvider).fetchBatchDetail(batchId),
  retry: _noRetry,
);

/// `GET platformPath(id, 'batches/steps?media_type=…')` — step catalog for
/// the New batch wizard's custom-pipeline step (keys + labels + defaults).
final stepCatalogProvider =
    FutureProvider.autoDispose.family<StepCatalog, String>(
  (Ref ref, String mediaType) =>
      ref.watch(processRepositoryProvider).fetchStepCatalog(mediaType: mediaType),
  retry: _noRetry,
);

/// `GET platformPath(id, 'step-profiles?media_type=…')` — saved profiles for
/// the wizard's profile step (02 §6; wired in backend `step_profiles.py`).
final stepProfilesProvider =
    FutureProvider.autoDispose.family<List<StepProfile>, String>(
  (Ref ref, String mediaType) =>
      ref.watch(processRepositoryProvider).fetchProfiles(mediaType: mediaType),
  retry: _noRetry,
);

/// Human line for a thrown object (same rule as gallery's `errorText`).
String processErrorText(Object error) =>
    error is AppException ? uiMessageFor(error) : 'Something went wrong.';
