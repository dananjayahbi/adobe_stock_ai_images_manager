import 'package:dio/dio.dart';

import '../../../core/utils/app_exception.dart';
import '../domain/gallery_group.dart';
import '../domain/gallery_page.dart';
import '../domain/gallery_query.dart';
import '../domain/gallery_repository.dart';
import '../domain/image_record.dart';
import 'gallery_api.dart';
import 'record_dto.dart';

/// Maps gallery JSON to domain models (03 §"API model → domain entity").
///
/// Per-row parsing is defensive (`RecordDto`): missing *fields* fall back to
/// null/empty defaults so one odd row never fails a whole page; a wrong
/// container (HTML error page, `null` body) throws [ServerException] so the
/// screen renders its inline ErrorView + retry instead of a silently empty
/// grid.
class GalleryRepositoryImpl implements GalleryRepository {
  GalleryRepositoryImpl(Dio dio, this._platformId)
      : _api = GalleryApi(dio);

  final GalleryApi _api;

  /// Captured at provider-build time; `galleryRepositoryProvider` watches
  /// `activePlatformIdProvider`, so a platform switch swaps this id and the
  /// controller re-fetches through the new `platformPath` prefix.
  final String _platformId;

  @override
  Future<GalleryPage> fetchPage(GalleryQuery query) async {
    final Map<String, Object?> map =
        _expectMap(await _api.records(_platformId, query));

    final List<ImageRecord> items = <ImageRecord>[];
    for (final Object? row in _list(map['items'])) {
      if (row is! Map<Object?, Object?>) {
        continue;
      }
      items.add(RecordDto(_stringKeyed(row)).toEntity());
    }

    // `total` drives the load-more cap; a payload missing it converges on
    // the visible count instead of promising rows that never arrive.
    final int total = map.containsKey('total')
        ? _int(map['total'])
        : items.length;

    return GalleryPage(items: items, total: total);
  }

  @override
  Future<ImageRecord> fetchById(String recordId) async {
    final Map<String, Object?> map =
        _expectMap(await _api.record(_platformId, recordId));
    return RecordDto(map).toEntity();
  }

  @override
  Future<List<GalleryGroup>> fetchGroups() async {
    final Map<String, Object?> map =
        _expectMap(await _api.groups(_platformId));

    final List<GalleryGroup> groups = <GalleryGroup>[];
    for (final Object? row in _list(map['items'])) {
      if (row is! Map<Object?, Object?>) {
        continue;
      }
      final Map<String, Object?> group = _stringKeyed(row);
      groups.add(
        GalleryGroup(
          id: group['id']?.toString() ?? '',
          name: group['name']?.toString() ?? '',
          count: group['image_count'] is num
              ? (group['image_count']! as num).toInt()
              : null,
        ),
      );
    }
    return groups;
  }

  @override
  Future<void> approve(
    String recordId, {
    String? overrideTitle,
    String? overrideDescription,
    List<String>? overrideKeywords,
  }) async {
    await _api.approve(
      _platformId,
      recordId,
      overrideTitle: overrideTitle,
      overrideDescription: overrideDescription,
      overrideKeywords: overrideKeywords,
    );
  }

  @override
  Future<void> markUsed(String recordId, {required bool used}) async {
    await _api.setUsed(_platformId, recordId, used: used);
  }

  @override
  Future<void> changeState(String recordId, String state) async {
    await _api.changeState(_platformId, recordId, state);
  }

  @override
  Future<void> resetStage(String recordId) async {
    await _api.resetStage(_platformId, recordId);
  }

  @override
  Future<void> deleteRecord(String recordId) async {
    await _api.deleteRecord(_platformId, recordId);
  }

  Map<String, Object?> _expectMap(Object? json) {
    if (json is Map<Object?, Object?>) {
      return _stringKeyed(json);
    }
    throw const ServerException(
      message: 'The studio server returned an unexpected payload.',
    );
  }

  Map<String, Object?> _stringKeyed(Map<Object?, Object?> map) =>
      map.map<String, Object?>(
        (Object? key, Object? value) =>
            MapEntry<String, Object?>(key?.toString() ?? '', value),
      );

  List<Object?> _list(Object? value) =>
      value is List<Object?> ? value : const <Object?>[];

  int _int(Object? value) => value is num ? value.toInt() : 0;
}
