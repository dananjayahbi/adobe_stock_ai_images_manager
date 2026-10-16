import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/dio_factory.dart';
import '../../../core/utils/ui_message.dart';
import '../domain/auth_repository.dart';
import 'auth_api.dart';

/// Auth repository wired to the shared Dio client (cookie jar + profile base
/// URL are handled by `core/network`).
final authRepositoryProvider = Provider<AuthRepository>(
  (ref) => AuthRepositoryImpl(ref.watch(dioProvider)),
);

/// Maps every escaping [DioException] through `mapDioError` so no raw Dio
/// error ever leaves `data/` (03 §4). [AuthApi] already absorbs the two
/// contract-level cases: 401 on the session probe and logout transport errors.
class AuthRepositoryImpl implements AuthRepository {
  AuthRepositoryImpl(Dio dio) : _api = AuthApi(dio);

  final AuthApi _api;

  @override
  Future<void> login(String username, String password) {
    return _guard(
      () => _api.login(username: username, password: password),
    );
  }

  @override
  Future<bool> sessionAlive() async {
    try {
      return await _api.me() != null;
    } on DioException catch (e) {
      throw mapDioError(e);
    }
  }

  @override
  Future<void> logout() async {
    try {
      await _api.logout();
    } on DioException {
      // Defensive: AuthApi swallows transport errors — logout never throws.
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
