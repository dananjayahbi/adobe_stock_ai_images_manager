import 'package:dio/dio.dart';

import '../../features/settings/domain/connection_profile.dart';

/// Rewrites the request base URL from the active connection profile on
/// **every** request, so switching profiles at runtime takes effect
/// immediately without rebuilding Dio (03 §3.2).
class BaseUrlInterceptor extends Interceptor {
  BaseUrlInterceptor(this.current);

  /// Reads the active profile provider at request time.
  final ConnectionProfile Function() current;

  @override
  void onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) {
    final String url = current().baseUrl;
    options.baseUrl = url.endsWith('/')
        ? url.substring(0, url.length - 1)
        : url;
    // Guard against `http://host` + `api/x` collapsing into a bad join.
    if (!options.path.startsWith('/') &&
        !options.path.startsWith('http')) {
      options.path = '/${options.path}';
    }
    handler.next(options);
  }
}
