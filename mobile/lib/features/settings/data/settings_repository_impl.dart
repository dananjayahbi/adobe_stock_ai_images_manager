import 'package:dio/dio.dart';

import '../../../core/utils/ui_message.dart';
import '../domain/settings_repository.dart';

/// Settings implementation over the shared Dio client (02 §8 endpoints,
/// cookie flows ride for free). Every escaping [DioException] is mapped
/// through `mapDioError` so no raw Dio error leaves `data/` (03 §4).
class SettingsRepositoryImpl implements SettingsRepository {
  SettingsRepositoryImpl(this._dio);

  final Dio _dio;

  @override
  Future<AppSettings> fetch() => _guard(() async {
        final Response<Map<String, dynamic>> response =
            await _dio.get<Map<String, dynamic>>('/api/settings');
        return AppSettings.fromJson(
          response.data ?? <String, dynamic>{},
        );
      });

  @override
  Future<AppSettings> update(Map<String, dynamic> patch) => _guard(() async {
        final Response<Map<String, dynamic>> response =
            await _dio.put<Map<String, dynamic>>('/api/settings', data: patch);
        return AppSettings.fromJson(
          response.data ?? <String, dynamic>{},
        );
      });

  @override
  Future<SettingsTestResult> test([Map<String, dynamic>? candidate]) =>
      _guard(() async {
        final Response<Map<String, dynamic>> response =
            await _dio.post<Map<String, dynamic>>(
          '/api/settings/test',
          // Null body = probe the saved config (backend contract).
          data: candidate,
        );
        return SettingsTestResult.fromJson(
          response.data ?? <String, dynamic>{},
        );
      });

  @override
  Future<AppSettings> reset() => _guard(() async {
        final Response<Map<String, dynamic>> response =
            await _dio.post<Map<String, dynamic>>('/api/settings/reset');
        return AppSettings.fromJson(
          response.data ?? <String, dynamic>{},
        );
      });

  @override
  Future<String?> fetchUsername() async {
    try {
      final Response<Map<String, dynamic>> response =
          await _dio.get<Map<String, dynamic>>('/api/auth/me');
      final Object? user = response.data?['user'];
      if (user is Map) {
        return user['username'] as String?;
      }
      return null;
    } on DioException catch (e) {
      // A 401 here simply means "no seat to show" — the note degrades to
      // the generic local-session line instead of failing the screen.
      if (e.response?.statusCode == 401) {
        return null;
      }
      throw mapDioError(e);
    }
  }

  Future<T> _guard<T>(Future<T> Function() call) async {
    try {
      return await call();
    } on DioException catch (e) {
      throw mapDioError(e);
    }
  }
}
