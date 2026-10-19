import 'dart:io';
import 'dart:math' as math;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path_provider/path_provider.dart';

import '../../../core/utils/app_exception.dart';
import '../../platforms/presentation/platforms_controller.dart';
import '../data/gallery_api.dart';
import '../domain/gallery_group.dart';
import '../domain/gallery_page.dart';
import '../domain/gallery_query.dart';
import '../domain/gallery_repository.dart';
import '../domain/image_record.dart';

/// Folder (group) cards for the gallery strip — fetched independently of
/// the image lens: image-level filters never hide a folder (web rule).
final galleryGroupsProvider = FutureProvider<List<GalleryGroup>>(
  (ref) => ref.watch(galleryRepositoryProvider).fetchGroups(),
  retry: _noRetry,
);

/// Gallery failures must surface **immediately** as the spec's error UI
/// (inline ErrorView over stale items, full ErrorView otherwise) — never
/// sit behind riverpod's default exponential auto-retry (up to ten silent
/// re-fetches ≈ 39 s of loading). Pull-to-refresh is the manual retry.
Duration? _noRetry(int retryCount, Object error) => null;

/// Gallery page state (05 §2.5): the current [GalleryQuery] lens plus the
/// paged [GalleryPage] it produced. Side-effect methods keep stale items on
/// failure (05 "error: grid keeps stale items") and rethrow so the screen
/// can surface the inline ErrorView; filter changes land in [AsyncError]
/// (riverpod keeps the previous page attached — the screen shows it with
/// an inline error until the new lens resolves).
final galleryControllerProvider =
    AsyncNotifierProvider<GalleryController, GalleryPage>(
  GalleryController.new,
  retry: _noRetry,
);

class GalleryController extends AsyncNotifier<GalleryPage> {
  /// Backend cap for one ZIP (`gallery_files.py MAX_ZIP_FILES`).
  static const int maxZipFiles = 200;

  /// Backend cap per page (`records.py MAX_LIMIT`).
  static const int maxPageLimit = 500;

  GalleryQuery _query = const GalleryQuery();

  /// Monotonic guard: every lens-changing fetch bumps it, and a completion
  /// carrying a stale id is dropped (web's useInfiniteRecords requestId).
  int _requestId = 0;

  bool _loadingMore = false;

  /// The lens currently driving the grid (chips render from it).
  GalleryQuery get query => _query;

  GalleryRepository get _repository => ref.read(galleryRepositoryProvider);

  @override
  Future<GalleryPage> build() async {
    // Platform switch → fresh fetch through the new platformPath prefix.
    ref.watch(activePlatformIdProvider);
    // A filter tap can land while this first fetch is still in flight;
    // re-fetch until the page we hold belongs to the lens that is current
    // *now*, so a slow response can never clobber a newer one.
    while (true) {
      final GalleryQuery lens = _query;
      final GalleryPage page = await _repository.fetchPage(lens);
      if (lens == _query) {
        return page;
      }
    }
  }

  /// Replaces the lens and refetches from offset 0 (skeleton flash — there
  /// is no stale page for a lens that never loaded). Never throws: the
  /// failure lands in the state the screen renders as its full ErrorView.
  Future<void> applyQuery(GalleryQuery next) async {
    _query = next.copyWith(offset: 0);
    final int requestId = ++_requestId;
    state = const AsyncLoading<GalleryPage>();
    try {
      final GalleryPage page = await _repository.fetchPage(_query);
      if (requestId == _requestId) {
        state = AsyncData<GalleryPage>(page);
      }
    } catch (error, stackTrace) {
      if (requestId == _requestId) {
        state = AsyncError<GalleryPage>(error, stackTrace);
      }
    }
  }

  /// Pull-to-refresh: refetches the first page of the current lens.
  /// Keeps stale items on failure and rethrows (05 "error: inline at grid
  /// top, grid keeps stale items"); with nothing to keep, the error becomes
  /// the full-page state instead.
  Future<void> refresh() async {
    final int requestId = ++_requestId;
    try {
      final GalleryPage page = await _repository.fetchPage(
        _query.copyWith(offset: 0),
      );
      _query = _query.copyWith(offset: 0);
      if (requestId == _requestId) {
        state = AsyncData<GalleryPage>(page);
      }
    } catch (error, stackTrace) {
      if (requestId != _requestId) {
        return;
      }
      if (!state.hasValue) {
        state = AsyncError<GalleryPage>(error, stackTrace);
      }
      rethrow;
    }
  }

  /// Sentinel-driven next page: appends and caps at `total`. No-op while a
  /// fetch is already in flight or while nothing is loaded; failures keep
  /// the stale items and rethrow for the screen's inline error.
  Future<void> loadMore() async {
    if (_loadingMore || state.isLoading) {
      return;
    }
    final GalleryPage? current = state.value;
    if (current == null || current.items.length >= current.total) {
      return;
    }

    _loadingMore = true;
    final int requestId = _requestId;
    try {
      // Next offset = rows already on screen — identical to offset + limit
      // after every full page, and still right when a page came back short.
      final GalleryPage next = await _repository.fetchPage(
        _query.copyWith(offset: current.items.length),
      );
      if (requestId != _requestId) {
        return;
      }
      if (next.items.isEmpty) {
        // The server has nothing past what we hold: converge the cap so the
        // sentinel stops asking instead of polling an unreachable offset.
        state = AsyncData<GalleryPage>(
          GalleryPage(items: current.items, total: current.items.length),
        );
        return;
      }
      state = AsyncData<GalleryPage>(
        GalleryPage(
          items: <ImageRecord>[...current.items, ...next.items],
          total: next.total,
        ),
      );
    } finally {
      _loadingMore = false;
    }
  }

  /// Refetches the whole loaded window after a mutation (mark used, delete,
  /// detail-screen approve) so scroll position survives: same rows come
  /// back in place, flags and totals corrected. Keeps stale items on
  /// failure and rethrows like [refresh].
  Future<void> reloadAfterMutation() async {
    final int requestId = ++_requestId;
    final GalleryPage? current = state.value;
    // Cover everything on screen (clamped to the backend's MAX_LIMIT) so
    // the list does not shrink under the reader just because a window grew.
    final int window = math.min(
      math.max(_query.limit, current?.items.length ?? 0),
      maxPageLimit,
    );
    try {
      final GalleryPage page = await _repository.fetchPage(
        _query.copyWith(offset: 0, limit: window),
      );
      if (requestId == _requestId) {
        state = AsyncData<GalleryPage>(page);
      }
    } catch (error, stackTrace) {
      if (requestId != _requestId) {
        return;
      }
      if (!state.hasValue) {
        state = AsyncError<GalleryPage>(error, stackTrace);
      }
      rethrow;
    }
  }

  /// Patches one row in place after a detail-screen mutation (approve,
  /// mark used, state change) so the grid reflects the fresh record with
  /// **zero** extra network traffic — the detail refetch already paid for
  /// one round trip. Rows outside the current lens are left alone (the
  /// next refresh re-evaluates membership).
  void patchRecord(ImageRecord updated) {
    final GalleryPage? current = state.value;
    if (current == null) {
      return;
    }
    final int at =
        current.items.indexWhere((ImageRecord row) => row.id == updated.id);
    if (at < 0) {
      return;
    }
    final List<ImageRecord> items = List<ImageRecord>.of(current.items);
    items[at] = updated;
    state = AsyncData<GalleryPage>(
      GalleryPage(items: items, total: current.total),
    );
  }

  /// Deletes the selection (single-record `DELETE`s — web would bulk), then
  /// reloads the window. Per-record failures are collected: the rest of the
  /// selection still gets its chance, the reload always runs, and the first
  /// error is rethrown for the caller's toast.
  Future<void> deleteRecords(List<String> recordIds) => _runSequential(
        recordIds,
        (String id) => _repository.deleteRecord(id),
      );

  /// Marks the selection used/unused in a single-record loop (web's bulk
  /// `PATCH /records/used` shares the body shape minus `record_ids`), then
  /// reloads. The caller keeps the selection — marking is not the end of
  /// the workflow (web gallery parity).
  Future<void> markRecordsUsed(
    List<String> recordIds, {
    required bool used,
  }) => _runSequential(
        recordIds,
        (String id) => _repository.markUsed(id, used: used),
      );

  /// `POST records/file-zip` → bytes → `documents/downloads/…zip`; returns
  /// the saved path for the success toast. Enforces the backend's 200-file
  /// cap up front so a doomed request never leaves the device.
  Future<String> downloadZip(List<String> recordIds) async {
    if (recordIds.isEmpty) {
      throw const ValidationException(message: 'Nothing is selected.');
    }
    if (recordIds.length > maxZipFiles) {
      throw const ValidationException(
        message: 'A ZIP holds at most $maxZipFiles images — narrow the selection.',
      );
    }
    final String platformId = ref.read(activePlatformIdProvider);
    final List<int> bytes = await ref
        .read(galleryApiProvider)
        .fileZip(platformId, recordIds);

    final Directory documents = await getApplicationDocumentsDirectory();
    final Directory downloads = Directory(
      '${documents.path}${Platform.pathSeparator}downloads',
    );
    await downloads.create(recursive: true);
    final File file = File(
      '${downloads.path}${Platform.pathSeparator}'
      'gallery-images-${DateTime.now().millisecondsSinceEpoch}.zip',
    );
    await file.writeAsBytes(bytes, flush: true);
    return file.path;
  }

  /// Runs [action] over [recordIds] sequentially: every record gets its
  /// attempt, the window reload always follows, and the first failure is
  /// rethrown with its original stack trace.
  Future<void> _runSequential(
    List<String> recordIds,
    Future<void> Function(String id) action,
  ) async {
    Object? firstError;
    StackTrace? firstStackTrace;
    for (final String id in recordIds) {
      try {
        await action(id);
      } catch (error, stackTrace) {
        firstError ??= error;
        firstStackTrace ??= stackTrace;
      }
    }
    try {
      await reloadAfterMutation();
    } catch (error, stackTrace) {
      firstError ??= error;
      firstStackTrace ??= stackTrace;
    }
    if (firstError != null) {
      Error.throwWithStackTrace(firstError, firstStackTrace!);
    }
  }
}
