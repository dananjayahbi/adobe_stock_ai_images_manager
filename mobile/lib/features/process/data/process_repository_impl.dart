import 'package:dio/dio.dart';

import '../../../core/utils/app_exception.dart';
import '../domain/batch.dart';
import '../domain/batch_step.dart';
import '../domain/process_repository.dart';
import 'batch_api.dart';
import 'batch_events_client.dart';

/// [ProcessRepository] over [BatchApi] (REST) + [BatchEventsClient] (SSE).
///
/// The platform id is captured at construction (the domain provider rebuilds
/// on `activePlatformIdProvider`), so every path runs through `platformPath`
/// (03 §3.5). The API returns raw JSON; this class is the single place where
/// that JSON becomes domain models — a wrong container is rejected here with
/// [ServerException] while field-level parsing stays defensive in the models
/// (M2 contract).
class ProcessRepositoryImpl implements ProcessRepository {
  ProcessRepositoryImpl(Dio dio, this.platformId)
      : _api = BatchApi(dio),
        _events = BatchEventsClient(dio);

  /// The platform every endpoint is scoped to.
  final String platformId;

  final BatchApi _api;
  final BatchEventsClient _events;

  @override
  Future<StepCatalog> fetchStepCatalog({String? mediaType}) async =>
      StepCatalog.fromJson(
        _expectMap(await _api.stepCatalog(platformId, mediaType: mediaType)),
      );

  @override
  Future<BatchList> fetchBatches({int limit = 50}) async => BatchList.fromJson(
        _expectMap(await _api.batches(platformId, limit: limit)),
      );

  @override
  Future<BatchDetail> fetchBatchDetail(String batchId) async =>
      BatchDetail.fromJson(
        _expectMap(await _api.batchDetail(platformId, batchId)),
      );

  @override
  Future<Batch> createBatch({
    required String name,
    required String mediaType,
    required List<BatchStep> steps,
    String? profileId,
  }) async =>
      Batch.fromJson(
        _expectMap(
          await _api.createBatch(
            platformId,
            name: name,
            mediaType: mediaType,
            steps: <Map<String, Object?>>[
              for (final BatchStep step in steps)
                <String, Object?>{'key': step.key, 'config': step.config},
            ],
            profileId: profileId,
          ),
        ),
      );

  @override
  Future<Batch> runBatch(String batchId) async => Batch.fromJson(
        _expectMap(await _api.runBatch(platformId, batchId)),
      );

  @override
  Future<Batch> cancelBatch(String batchId) async => Batch.fromJson(
        _expectMap(await _api.cancelBatch(platformId, batchId)),
      );

  @override
  Future<void> deleteBatch(String batchId) =>
      _api.deleteBatch(platformId, batchId);

  @override
  Future<List<StepProfile>> fetchProfiles({String? mediaType}) async {
    final Map<String, Object?> body = _expectMap(
      await _api.profiles(platformId, mediaType: mediaType),
    );
    final List<StepProfile> profiles = <StepProfile>[];
    final Object? rows = body['items'];
    if (rows is List<Object?>) {
      for (final Object? row in rows) {
        if (row is Map<Object?, Object?>) {
          profiles.add(
            StepProfile.fromJson(
              row.map<String, Object?>(
                (Object? key, Object? value) =>
                    MapEntry<String, Object?>(key?.toString() ?? '', value),
              ),
            ),
          );
        }
      }
    }
    return profiles;
  }

  @override
  Future<StepProfile> createProfile({
    required String name,
    required String mediaType,
    required List<BatchStep> steps,
  }) async =>
      StepProfile.fromJson(
        _expectMap(
          await _api.createProfile(
            platformId,
            name: name,
            mediaType: mediaType,
            steps: <Map<String, Object?>>[
              for (final BatchStep step in steps)
                <String, Object?>{'key': step.key, 'config': step.config},
            ],
          ),
        ),
      );

  @override
  Stream<BatchSnapshot> watchBatch(String batchId) =>
      _events.watchBatch(platformId, batchId);

  static Map<String, Object?> _expectMap(Object? data) {
    if (data is Map<String, Object?>) {
      return data;
    }
    throw const ServerException(message: 'Unexpected response shape');
  }
}
