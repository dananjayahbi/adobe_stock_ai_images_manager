import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/dio_factory.dart';
import '../../../core/utils/app_exception.dart';
import '../domain/delivery_item.dart';
import '../domain/delivery_repository.dart';
import 'delivery_api.dart';

/// Repository wired to the shared Dio client (cookie jar + profile base URL
/// handled by `core/network`). **Test override seam:** widget tests replace
/// this provider with a fake backend — Dio and path_provider never run.
final deliveryRepositoryProvider = Provider<DeliveryRepository>(
  (ref) => DeliveryRepositoryImpl(ref.watch(dioProvider)),
);

/// Maps delivery JSON/bytes to domain models (03 §"API model → domain
/// entity").
///
/// Parsing is defensive per the M2 contract: missing *fields* fall back to
/// zero/empty/null defaults so one odd row never fails a whole list; a wrong
/// container (HTML error page, `null` body) throws [ServerException] so the
/// screen renders its inline ErrorView + retry instead of fake emptiness.
class DeliveryRepositoryImpl implements DeliveryRepository {
  DeliveryRepositoryImpl(Dio dio) : _api = DeliveryApi(dio);

  final DeliveryApi _api;

  @override
  Future<List<DeliveryCandidate>> fetchCandidates(String platformId) async {
    final Map<String, Object?> map =
        _expectMap(await _api.candidates(platformId));

    final List<DeliveryCandidate> rows = <DeliveryCandidate>[];
    for (final Object? row in _list(map['items'])) {
      if (row is! Map<Object?, Object?>) continue;
      final String id = _text(row['id']);
      // An id-less row can never be selected or bundled — skip it rather
      // than surface a row whose checkbox would be a lie.
      if (id.isEmpty) continue;
      rows.add(
        DeliveryCandidate(
          id: id,
          filename: _text(row['filename']),
          stage: _text(row['stage']),
          state: _text(row['state']),
          uploadFilename: _textOrNull(row['upload_filename']),
          title: _textOrNull(row['generated_title']),
          isUsed: row['is_used'] == true,
        ),
      );
    }
    return rows;
  }

  @override
  Future<CsvPreview> previewCsv(
    String platformId, {
    List<String>? recordIds,
  }) async {
    final Map<String, Object?> map = _expectMap(
      await _api.csvPreview(
        platformId,
        recordIds: recordIds,
        // Web parity (`lib/delivery.ts`): an explicit selection is exported
        // as-picked (`only_ready: false`); "everything eligible" defaults on.
        onlyReady: recordIds == null,
      ),
    );
    return CsvPreview(
      csvText: _text(map['csv_text']),
      rowCount: _int(map['row_count']),
      skipped: _stringList(map['skipped']),
      warnings: _stringList(map['warnings']),
    );
  }

  @override
  Future<DeliveryFile> exportCsv(
    String platformId, {
    List<String>? recordIds,
  }) async {
    final Response<List<int>> response = await _api.csvExport(
      platformId,
      recordIds: recordIds,
      onlyReady: recordIds == null,
    );
    return _file(response, fallback: 'adobe-stock-metadata.csv');
  }

  @override
  Future<DeliveryFile> bundleZip(
    String platformId, {
    required List<String> recordIds,
  }) async {
    final Response<List<int>> response = await _api.bundle(
      platformId,
      recordIds: recordIds,
    );
    return _file(response, fallback: 'adobe-stock-delivery.zip');
  }

  @override
  Future<ForceAcceptOutcome> forceAccept(
    String platformId, {
    required List<String> recordIds,
    required String reason,
  }) async {
    final Map<String, Object?> map = _expectMap(
      await _api.forceAccept(
        platformId,
        recordIds: recordIds,
        reason: reason,
      ),
    );

    final List<ForceAcceptItem> items = <ForceAcceptItem>[];
    for (final Object? row in _list(map['items'])) {
      if (row is! Map<Object?, Object?>) continue;
      items.add(
        ForceAcceptItem(
          recordId: _text(row['record_id']),
          accepted: row['accepted'] == true,
          previousStage: _text(row['previous_stage']),
          newStage: _textOrNull(row['new_stage']),
          score: _doubleOrNull(row['score']),
          reason: _text(row['reason']),
        ),
      );
    }

    final int accepted = map.containsKey('accepted')
        ? _int(map['accepted'])
        : items.where((ForceAcceptItem i) => i.accepted).length;
    return ForceAcceptOutcome(
      items: items,
      accepted: accepted,
      // Server sends `refused`; recomputing keeps a partial payload honest.
      refused: map.containsKey('refused')
          ? _int(map['refused'])
          : items.length - accepted,
    );
  }

  @override
  Future<RenameOutcome> suggestNames(
    String platformId, {
    required List<RenameEntry> items,
    bool regenerate = false,
  }) => _rename(
        _api.renameSuggest(
          platformId,
          items: items,
          regenerate: regenerate,
        ),
      );

  @override
  Future<RenameOutcome> applySuggestedNames(
    String platformId, {
    required List<RenameEntry> items,
    bool regenerate = false,
  }) => _rename(
        _api.applySuggestedNames(
          platformId,
          items: items,
          regenerate: regenerate,
        ),
      );

  @override
  Future<RenameOutcome> rename(
    String platformId, {
    required List<RenameEntry> items,
    bool regenerate = false,
  }) => _rename(
        _api.rename(
          platformId,
          items: items,
          regenerate: regenerate,
        ),
      );

  Future<RenameOutcome> _rename(Future<Object?> request) async {
    final Map<String, Object?> map = _expectMap(await request);
    final List<RenameResultItem> rows = <RenameResultItem>[];
    for (final Object? row in _list(map['items'])) {
      if (row is! Map<Object?, Object?>) continue;
      rows.add(
        RenameResultItem(
          recordId: _text(row['record_id']),
          filename: _text(row['filename']),
          downloadName: _textOrNull(row['download_name']),
          changed: row['changed'] == true,
          error: _textOrNull(row['error']),
        ),
      );
    }
    return RenameOutcome(
      items: rows,
      updated: _int(map['updated']),
      failed: _int(map['failed']),
    );
  }

  /// Bytes + server filename from `Content-Disposition:
  /// attachment; filename="…"` (captured live on :8002); the fallback keeps
  /// a headerless 200 saveable anyway.
  DeliveryFile _file(Response<List<int>> response, {required String fallback}) {
    final String? disposition = _header(response.headers, 'content-disposition');
    final Match? match =
        disposition == null ? null : RegExp(r'filename="?([^";]+)"?').firstMatch(disposition);
    return DeliveryFile(
      fileName: match?.group(1) ?? fallback,
      bytes: response.data ?? const <int>[],
    );
  }

  String? _header(Headers headers, String name) {
    for (final MapEntry<String, List<String>> entry in headers.map.entries) {
      if (entry.key.toLowerCase() == name) {
        return entry.value.join('; ');
      }
    }
    return null;
  }

  Map<String, Object?> _expectMap(Object? json) {
    if (json is Map<Object?, Object?>) {
      return json.map<String, Object?>(
        (Object? key, Object? value) => MapEntry<String, Object?>(
          key?.toString() ?? '',
          value,
        ),
      );
    }
    throw const ServerException(
      message: 'The studio server returned an unexpected payload.',
    );
  }

  List<Object?> _list(Object? value) =>
      value is List<Object?> ? value : const <Object?>[];

  List<String> _stringList(Object? value) => _list(value)
      .map((Object? row) => row?.toString() ?? '')
      .where((String row) => row.isNotEmpty)
      .toList();

  int _int(Object? value) => value is num ? value.toInt() : 0;

  double? _doubleOrNull(Object? value) => value is num ? value.toDouble() : null;

  String? _textOrNull(Object? value) => value is String && value.isNotEmpty
      ? value
      : null;

  String _text(Object? value) => value?.toString() ?? '';
}
