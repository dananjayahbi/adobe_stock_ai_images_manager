import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/dio_factory.dart';
import '../../../core/utils/ui_message.dart';
import '../domain/platform.dart';
import '../domain/platform_repository.dart';
import 'platform_api.dart';

/// Platform catalogue repository wired to the shared Dio client (cookie jar
/// + profile base URL come from `core/network`).
final platformRepositoryProvider = Provider<PlatformRepository>(
  (ref) => PlatformRepositoryImpl(ref.watch(dioProvider)),
);

/// Maps every escaping [DioException] through `mapDioError` so no raw Dio
/// error ever leaves `data/` (03 §4), then converts catalogue JSON into
/// domain [PlatformEntry]s.
class PlatformRepositoryImpl implements PlatformRepository {
  PlatformRepositoryImpl(Dio dio) : _api = PlatformApi(dio);

  final PlatformApi _api;

  @override
  Future<List<PlatformEntry>> fetchPlatforms() async {
    final List<Object?> items = await _guard(_api.fetchPlatformList);
    return items
        .whereType<Map<String, Object?>>()
        .map(PlatformEntry.fromJson)
        .toList(growable: false);
  }

  @override
  Future<PlatformEntry> fetchPlatform(String platformId) async {
    final Map<String, Object?> json =
        await _guard(() => _api.fetchPlatform(platformId));
    return PlatformEntry.fromJson(json);
  }

  Future<T> _guard<T>(Future<T> Function() call) async {
    try {
      return await call();
    } on DioException catch (e) {
      throw mapDioError(e);
    }
  }
}
