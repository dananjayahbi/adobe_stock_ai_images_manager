import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/dio_factory.dart';
import '../../../core/utils/app_exception.dart';
import '../../../core/utils/platform_paths.dart';
import '../../../core/utils/ui_message.dart';
import '../domain/delivery_item.dart';

/// App-wide handle on the delivery data source.
final deliveryApiProvider = Provider<DeliveryApi>(
  (ref) => DeliveryApi(ref.watch(dioProvider)),
);

/// Thin Dio data source for the seven delivery endpoints (02 §7) plus the
/// records listing that supplies their `record_ids`.
///
/// Every path is built with `platformPath` so a platform switch flips all
/// endpoints at once (03 §3.5); raw JSON/bytes come back untouched and
/// `DeliveryRepositoryImpl` maps them to domain models. `DioException`s are
/// mapped here with `mapDioError` — no raw Dio error leaves `data/` (03 §4).
///
/// Note: 05 §2.8 writes the preview as `GET …`; the backend (and this
/// client) use **POST** — backend wins. Caps: bundle ≤ 50 files, one call
/// ≤ 500 records (`MAX_ZIP_FILES` / `MAX_DELIVERY_BATCH`).
class DeliveryApi {
  DeliveryApi(this._dio);

  final Dio _dio;

  /// `GET /api/records?limit=500` → `{items, total, page, page_size}`.
  Future<Object?> candidates(String platformId) => _get(
        platformPath(platformId, 'records?limit=500'),
      );

  /// `POST /api/assets/csv/preview` → `{csv_text, row_count, skipped,
  /// warnings}` — no side effects (`apply_names` stays off server-side).
  Future<Object?> csvPreview(
    String platformId, {
    required List<String>? recordIds,
    required bool onlyReady,
  }) => _post(
        platformPath(platformId, 'assets/csv/preview'),
        data: _csvBody(recordIds, onlyReady),
      );

  /// `POST /api/assets/csv` → CSV bytes with `Content-Disposition` and the
  /// `X-Csv-*` counters (409 `{"detail": …}` when nothing is exportable).
  Future<Response<List<int>>> csvExport(
    String platformId, {
    required List<String>? recordIds,
    required bool onlyReady,
  }) => _postBytes(
        platformPath(platformId, 'assets/csv'),
        data: _csvBody(recordIds, onlyReady),
      );

  /// `POST /api/assets/bundle` → `application/zip` for an explicit
  /// selection (400 on an empty list, 409 when no selected file exists).
  Future<Response<List<int>>> bundle(
    String platformId, {
    required List<String> recordIds,
  }) => _postBytes(
        platformPath(platformId, 'assets/bundle'),
        data: <String, Object?>{
          'record_ids': recordIds,
          'only_ready': false,
        },
      );

  /// `POST /api/assets/force-accept` → `ForcedAcceptResponse
  /// {items[], accepted, refused}`.
  Future<Object?> forceAccept(
    String platformId, {
    required List<String> recordIds,
    required String reason,
  }) => _post(
        platformPath(platformId, 'assets/force-accept'),
        data: <String, Object?>{
          'record_ids': recordIds,
          'reason': reason,
        },
      );

  /// `POST /api/assets/rename` → `RenameResponse {items[], updated,
  /// failed}`; `regenerate` rebuilds every name from the title, ignoring
  /// `items`.
  Future<Object?> rename(
    String platformId, {
    required List<RenameEntry> items,
    required bool regenerate,
  }) => _post(
        platformPath(platformId, 'assets/rename'),
        data: _renameBody(items, regenerate),
      );

  /// `POST /api/assets/rename-suggest` — dry run, same body shape.
  Future<Object?> renameSuggest(
    String platformId, {
    required List<RenameEntry> items,
    required bool regenerate,
  }) => _post(
        platformPath(platformId, 'assets/rename-suggest'),
        data: _renameBody(items, regenerate),
      );

  /// `POST /api/assets/apply-suggested-names` — same body shape.
  Future<Object?> applySuggestedNames(
    String platformId, {
    required List<RenameEntry> items,
    required bool regenerate,
  }) => _post(
        platformPath(platformId, 'assets/apply-suggested-names'),
        data: _renameBody(items, regenerate),
      );

  /// `CsvExportRequest {record_ids, only_ready}` — both keys always ride,
  /// `record_ids: null` meaning "every eligible record".
  Map<String, Object?> _csvBody(List<String>? recordIds, bool onlyReady) =>
      <String, Object?>{
        'record_ids': recordIds,
        'only_ready': onlyReady,
      };

  /// `RenameRequest {items: [{record_id, name}], regenerate}`.
  Map<String, Object?> _renameBody(List<RenameEntry> items, bool regenerate) =>
      <String, Object?>{
        'items': items
            .map(
              (RenameEntry e) =>
                  <String, Object?>{'record_id': e.recordId, 'name': e.name},
            )
            .toList(),
        'regenerate': regenerate,
      };

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

  /// Byte download (cookie rides the shared Dio jar): returns headers +
  /// bytes so the repository can read `Content-Disposition`.
  Future<Response<List<int>>> _postBytes(String path, {Object? data}) async {
    try {
      final Response<List<int>> response = await _dio.post<List<int>>(
        path,
        data: data,
        options: Options(responseType: ResponseType.bytes),
      );
      return response;
    } on DioException catch (e) {
      throw _mapByteError(e);
    }
  }

  /// Byte responses carry error bodies as raw bytes, which `mapDioError`
  /// cannot read — decode FastAPI's `{"detail": …}` first so a 409 still
  /// surfaces the server's real sentence instead of "Http status error".
  AppException _mapByteError(DioException e) {
    final Object? body = e.response?.data;
    if (body is List<int>) {
      try {
        final Object? decoded = jsonDecode(
          utf8.decode(body, allowMalformed: true),
        );
        if (decoded is Map<Object?, Object?> && decoded['detail'] != null) {
          return mapDioError(
            DioException(
              requestOptions: e.requestOptions,
              response: Response<Object?>(
                requestOptions: e.requestOptions,
                statusCode: e.response?.statusCode,
                data: <String, Object?>{
                  'detail': decoded['detail'].toString(),
                },
              ),
              type: e.type,
            ),
          );
        }
      } on FormatException {
        // Binary junk — fall through to the generic mapping.
      }
    }
    return mapDioError(e);
  }
}
