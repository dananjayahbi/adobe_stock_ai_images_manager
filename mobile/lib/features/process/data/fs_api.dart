import 'package:dio/dio.dart';

import '../../../core/utils/platform_paths.dart';
import '../../../core/utils/ui_message.dart';

/// Thin Dio data source for the source-folder file browser (M4 picker
/// flow, backend `fs.py`).
///
/// Paths are built with `platformPath` so a platform switch flips all
/// endpoints (03 §3.5); raw JSON comes back untouched and
/// `FsRepositoryImpl` maps it to domain models. `DioException`s are mapped
/// here with `mapDioError` — no raw Dio error leaves `data/` (03 §4).
///
/// Endpoint list (contract): `GET fs/root` → `{configured, path, exists}`,
/// `GET fs/list?path=rel` → one directory listing (jpg/jpeg/png only),
/// `GET fs/thumb?path=rel` → JPEG thumbnail (max 512). Errors: 400
/// unconfigured, 403 path escape, 404 missing.
class FsApi {
  FsApi(this._dio);

  final Dio _dio;

  /// `GET fs/root` → `{configured, path|null, exists}`.
  Future<Object?> fsRoot(String platformId) =>
      _get(platformPath(platformId, 'fs/root'));

  /// `GET fs/list?path=rel` → `{path, segments[], parent|null, dirs[],
  /// files[]}`; `path` may be `''` for the configured root (the query is
  /// always sent so a required-parameter backend sees an explicit value).
  Future<Object?> fsList(String platformId, String path) => _get(
    platformPath(platformId, 'fs/list?path=${Uri.encodeQueryComponent(path)}'),
  );

  /// `GET fs/thumb?path=rel` — the URL `Image.network` loads (Dio is not
  /// involved, so the caller prefixes the profile base URL and the session
  /// cookie itself).
  static String fsThumbUrl(String platformId, String path) => platformPath(
    platformId,
    'fs/thumb?path=${Uri.encodeQueryComponent(path)}',
  );

  Future<Object?> _get(String path) async {
    try {
      final Response<Object?> response = await _dio.get<Object?>(path);
      return response.data;
    } on DioException catch (e) {
      throw mapDioError(e);
    }
  }
}
