import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/dio_factory.dart';
import '../../../core/utils/platform_paths.dart';
import '../../../core/utils/ui_message.dart';
import '../domain/gallery_query.dart';

/// App-wide handle on the gallery data source (zip download lives here —
/// the repository contract is reads + single-record mutations only).
final galleryApiProvider = Provider<GalleryApi>(
  (ref) => GalleryApi(ref.watch(dioProvider)),
);

/// Thin Dio data source for the gallery endpoints (02 §3).
///
/// Every path is built with `platformPath` so a platform switch flips all
/// endpoints at once (03 §3.5); raw JSON comes back untouched and
/// `GalleryRepositoryImpl` maps it to domain models. `DioException`s are
/// mapped here with `mapDioError` — no raw Dio error leaves `data/` (03 §4).
class GalleryApi {
  GalleryApi(this._dio);

  final Dio _dio;

  /// `GET /api/records?…` — parameter set and encoding mirror
  /// `frontend-new/src/lib/records.ts#fetchRecords` (no `sort`, `used`
  /// omitted for `'all'`, `group_id` always present, `state` as CSV).
  Future<Object?> records(String platformId, GalleryQuery query) => _get(
        platformPath(platformId, 'records?${_encodeQuery(query.toQuery())}'),
      );

  /// `GET /api/records/{id}` → one `RecordResponse`.
  Future<Object?> record(String platformId, String recordId) =>
      _get(platformPath(platformId, 'records/$recordId'));

  /// `GET /api/groups` → `{items: [{id, name, image_count, created_at}]}`.
  Future<Object?> groups(String platformId) =>
      _get(platformPath(platformId, 'groups'));

  /// `POST /api/records/{id}/approve` — body only when an override rides
  /// along (`ApproveRequest | None` accepts the empty call).
  Future<Object?> approve(
    String platformId,
    String recordId, {
    String? overrideTitle,
    String? overrideDescription,
    List<String>? overrideKeywords,
  }) {
    final Map<String, Object?> body = <String, Object?>{
      'override_title': ?overrideTitle,
      'override_description': ?overrideDescription,
      'override_keywords': ?overrideKeywords,
    };
    return _post(
      platformPath(platformId, 'records/$recordId/approve'),
      data: body.isEmpty ? null : body,
    );
  }

  /// `PATCH /api/records/{id}/used` — `UsedRequest {is_used}` (web's bulk
  /// shape is `{record_ids, is_used}`; the contract exposes single-record).
  Future<Object?> setUsed(
    String platformId,
    String recordId, {
    required bool used,
  }) => _patch(
        platformPath(platformId, 'records/$recordId/used'),
        data: <String, Object?>{'is_used': used},
      );

  /// `PATCH /api/records/{id}/state` — `StateRequest {state}`; 200 with the
  /// full record, 400 when the transition is not allowed.
  Future<Object?> changeState(
    String platformId,
    String recordId,
    String state,
  ) => _patch(
        platformPath(platformId, 'records/$recordId/state'),
        data: <String, Object?>{'state': state},
      );

  /// `POST /api/records/{id}/reset-stage` (no body; 409 once PUBLISHED).
  Future<Object?> resetStage(String platformId, String recordId) => _post(
        platformPath(platformId, 'records/$recordId/reset-stage'),
      );

  /// `DELETE /api/records/{id}` — removes the row plus its files.
  Future<Object?> deleteRecord(String platformId, String recordId) =>
      _delete(platformPath(platformId, 'records/$recordId'));

  /// `POST /api/records/file-zip` → raw ZIP bytes of the selection
  /// (backend caps at 200 ids; distinct from the READY-only `download-zip`).
  Future<List<int>> fileZip(String platformId, List<String> recordIds) async {
    try {
      final Response<List<int>> response = await _dio.post<List<int>>(
        platformPath(platformId, 'records/file-zip'),
        data: <String, Object?>{'record_ids': recordIds},
        options: Options(responseType: ResponseType.bytes),
      );
      return response.data ?? const <int>[];
    } on DioException catch (e) {
      throw mapDioError(e);
    }
  }

  Future<Object?> _get(String path) async {
    try {
      final Response<dynamic> response = await _dio.get<dynamic>(path);
      return response.data;
    } on DioException catch (e) {
      throw mapDioError(e);
    }
  }

  Future<Object?> _post(String path, {Object? data}) async {
    try {
      final Response<dynamic> response =
          await _dio.post<dynamic>(path, data: data);
      return response.data;
    } on DioException catch (e) {
      throw mapDioError(e);
    }
  }

  Future<Object?> _patch(String path, {Object? data}) async {
    try {
      final Response<dynamic> response =
          await _dio.patch<dynamic>(path, data: data);
      return response.data;
    } on DioException catch (e) {
      throw mapDioError(e);
    }
  }

  Future<Object?> _delete(String path) async {
    try {
      final Response<dynamic> response = await _dio.delete<dynamic>(path);
      return response.data;
    } on DioException catch (e) {
      throw mapDioError(e);
    }
  }
}

/// Joins pre-encoded `key=value` pairs in the map's insertion order — the
/// order `frontend-new`'s params object serialises in, so both clients hit
/// byte-identical URLs.
String _encodeQuery(Map<String, String> params) => params.entries
    .map((MapEntry<String, String> e) =>
        '${_encodeComponent(e.key)}=${_encodeComponent(e.value)}')
    .join('&');

/// Percent-encodes one query component the way axios' default serialiser
/// does: `Uri.encodeQueryComponent` first, then the escapes axios undoes
/// (`:` `$` `,` `[` `]`) with space as `+`. The state CSV therefore travels
/// as a literal comma (`state=READY_TO_PUBLISH,PUBLISHED`) — same bytes the
/// web sends — and user search text stays fully encoded.
///
/// Encoding happens before the un-escape pass, so a literal `%2C` inside a
/// search term arrives as `%252C` and can never be mistaken for the
/// comma-escape this method deliberately reverts.
String _encodeComponent(String value) => Uri.encodeQueryComponent(value)
    .replaceAll('%3A', ':')
    .replaceAll('%24', r'$')
    .replaceAll('%2C', ',')
    .replaceAll('%20', '+')
    .replaceAll('%5B', '[')
    .replaceAll('%5D', ']');
