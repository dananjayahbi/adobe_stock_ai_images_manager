import 'package:dio/dio.dart';

/// Thin Dio data source for the platform catalogue (03 §4) — no error
/// mapping here; raw `DioException`s propagate to the repository.
class PlatformApi {
  PlatformApi(this._dio);

  final Dio _dio;

  /// `GET /api/platforms/` — **the trailing slash is mandatory**: the route
  /// is registered as `"/"` under the `/api/platforms` prefix, so the bare
  /// path only answers via a 307 redirect that naive clients drop (02 §2).
  Future<List<Object?>> fetchPlatformList() async {
    final Object? data = (await _dio.get<List<Object?>>('/api/platforms/'))
        .data;
    if (data is List<Object?>) {
      return data;
    }
    return const <Object?>[];
  }

  /// `GET /api/platforms/{platform_id}` — one catalogue entry; the backend
  /// 404s with `{"detail": "Unknown platform"}` for anything not registered.
  Future<Map<String, Object?>> fetchPlatform(String platformId) async {
    final Object? data =
        (await _dio.get<Map<String, Object?>>('/api/platforms/$platformId'))
            .data;
    if (data is Map<String, Object?>) {
      return data;
    }
    return <String, Object?>{};
  }
}
