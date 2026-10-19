import 'package:dio/dio.dart';

import '../../../core/utils/app_exception.dart';
import '../domain/fs_repository.dart';
import 'fs_api.dart';

/// [FsRepository] over [FsApi] — the source-folder browser's single place
/// where raw JSON becomes domain models (wrong container →
/// [ServerException]; field parsing stays defensive in the models, M2
/// contract). The platform id is captured at construction, so every path
/// runs through `platformPath` (03 §3.5).
class FsRepositoryImpl implements FsRepository {
  FsRepositoryImpl(Dio dio, this.platformId) : _api = FsApi(dio);

  /// The platform every endpoint is scoped to.
  final String platformId;

  final FsApi _api;

  @override
  Future<FsRoot> fetchRoot() async =>
      FsRoot.fromJson(_expectMap(await _api.fsRoot(platformId)));

  @override
  Future<FsListing> fetchListing(String path) async => FsListing.fromJson(
    _expectMap(await _api.fsList(platformId, path)),
    fallbackPath: path,
  );

  @override
  String thumbUrl(String path) => FsApi.fsThumbUrl(platformId, path);

  static Map<String, Object?> _expectMap(Object? data) {
    if (data is Map<String, Object?>) {
      return data;
    }
    throw const ServerException(message: 'Unexpected response shape');
  }
}
