import 'package:ai_stock_studio/features/process/data/process_repository_impl.dart';
import 'package:ai_stock_studio/features/process/domain/batch.dart';
import 'package:ai_stock_studio/features/process/domain/batch_step.dart';
import 'package:ai_stock_studio/features/platforms/presentation/platforms_controller.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/dio_factory.dart';

/// Repository wired to the shared Dio client (cookie jar + profile base URL
/// handled by `core/network`). Widget tests override this provider to fake
/// the backend — the process feature's single override seam (same shape as
/// `galleryRepositoryProvider`).
///
/// The active platform id is captured when the provider builds, so every
/// path runs through `platformPath(activePlatformId, …)` (03 §3.5).
final processRepositoryProvider = Provider<ProcessRepository>((ref) {
  final String platformId = ref.watch(activePlatformIdProvider);
  return ProcessRepositoryImpl(ref.watch(dioProvider), platformId);
});

/// Contract for the batch pipeline API (02 §6, backend `batches.py` +
/// `step_profiles.py`). Implemented by `ProcessRepositoryImpl`.
abstract class ProcessRepository {
  /// `GET platformPath(id, 'batches/steps?...')` — step catalog.
  Future<StepCatalog> fetchStepCatalog({String? mediaType});

  /// `GET platformPath(id, 'batches?limit=...')` — `{items, total}`.
  Future<BatchList> fetchBatches({int limit = 50});

  /// `GET platformPath(id, 'batches/{batchId}')` — `BatchDetailResponse`.
  Future<BatchDetail> fetchBatchDetail(String batchId);

  /// `POST platformPath(id, 'batches')` → 201 `BatchResponse` (draft).
  Future<Batch> createBatch({
    required String name,
    required String mediaType,
    required List<BatchStep> steps,
    String? profileId,
  });

  /// `POST platformPath(id, 'batches/{batchId}/run')` → `BatchResponse`.
  Future<Batch> runBatch(String batchId);

  /// `POST platformPath(id, 'batches/{batchId}/cancel')` → `BatchResponse`.
  Future<Batch> cancelBatch(String batchId);

  /// `DELETE platformPath(id, 'batches/{batchId}')` → 204.
  Future<void> deleteBatch(String batchId);

  /// `GET platformPath(id, 'step-profiles?...')` — `{items, total}`.
  Future<List<StepProfile>> fetchProfiles({String? mediaType});

  /// `POST platformPath(id, 'step-profiles')` → 201 `ProfileResponse`
  /// (batch detail's "Save as profile").
  Future<StepProfile> createProfile({
    required String name,
    required String mediaType,
    required List<BatchStep> steps,
  });

  /// Live snapshots from `GET platformPath(id, 'batches/{batchId}/events')`.
  ///
  /// SSE → `BatchSnapshot` (frames are `BatchResponse`, no `records`);
  /// closes on the terminal `event: done`.
  Stream<BatchSnapshot> watchBatch(String batchId);
}
