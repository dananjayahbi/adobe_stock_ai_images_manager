import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ai_stock_studio/core/utils/app_exception.dart';
import 'package:ai_stock_studio/features/gallery/domain/gallery_group.dart';
import 'package:ai_stock_studio/features/gallery/domain/gallery_page.dart';
import 'package:ai_stock_studio/features/gallery/domain/gallery_query.dart';
import 'package:ai_stock_studio/features/gallery/domain/gallery_repository.dart';
import 'package:ai_stock_studio/features/gallery/domain/image_record.dart';
import 'package:ai_stock_studio/features/gallery/presentation/gallery_controller.dart';

ImageRecord _record(String id, {String? filename}) => ImageRecord(
      id: id,
      filename: filename ?? '$id.jpg',
      status: 'PASSED',
    );

/// A page of [size] rows starting at the query's offset, capped at [total].
GalleryPage _pageAt(int offset, int total, {int size = 2}) {
  int count = total - offset;
  if (count > size) {
    count = size;
  }
  if (count < 0) {
    count = 0;
  }
  return GalleryPage(
    items: <ImageRecord>[
      for (int i = 0; i < count; i++) _record('r${offset + i}'),
    ],
    total: total,
  );
}

class _FakeGalleryRepository implements GalleryRepository {
  final List<GalleryQuery> pageQueries = <GalleryQuery>[];
  final List<String> deleteCalls = <String>[];
  final List<({String id, bool used})> usedCalls = <({String id, bool used})>[];

  GalleryPage Function(GalleryQuery query)? onFetchPage;
  List<GalleryGroup> groups = const <GalleryGroup>[];
  Object? pageError;
  final Set<String> deleteErrors = <String>{};

  /// When set, every fetchPage awaits it — drives loading-state tests.
  Completer<void>? gate;

  Future<GalleryPage> _fetch(GalleryQuery query) async {
    pageQueries.add(query);
    final Completer<void>? pending = gate;
    if (pending != null) {
      await pending.future;
    }
    if (pageError != null) {
      throw pageError!; // ignore: only_throw_errors — fake failure injection
    }
    return onFetchPage?.call(query) ?? const GalleryPage(items: <ImageRecord>[], total: 0);
  }

  @override
  Future<GalleryPage> fetchPage(GalleryQuery query) => _fetch(query);

  @override
  Future<ImageRecord> fetchById(String recordId) async => _record(recordId);

  @override
  Future<List<GalleryGroup>> fetchGroups() async => groups;

  @override
  Future<void> approve(
    String recordId, {
    String? overrideTitle,
    String? overrideDescription,
    List<String>? overrideKeywords,
  }) async {}

  @override
  Future<void> markUsed(String recordId, {required bool used}) async {
    usedCalls.add((id: recordId, used: used));
  }

  @override
  Future<void> changeState(String recordId, String state) async {}

  @override
  Future<void> resetStage(String recordId) async {}

  @override
  Future<void> deleteRecord(String recordId) async {
    deleteCalls.add(recordId);
    if (deleteErrors.contains(recordId)) {
      throw const ServerException(message: 'gone');
    }
  }
}

void main() {
  late _FakeGalleryRepository repo;
  late ProviderContainer container;

  setUp(() {
    repo = _FakeGalleryRepository();
    container = ProviderContainer(
      overrides: [
        galleryRepositoryProvider.overrideWithValue(repo),
      ],
    );
    addTearDown(container.dispose);
  });

  GalleryController notifier() =>
      container.read(galleryControllerProvider.notifier);

  Future<GalleryPage> load() =>
      container.read(galleryControllerProvider.future);

  GalleryPage state() => container.read(galleryControllerProvider).value!;

  test('build loads the default web lens from offset 0', () async {
    repo.onFetchPage = (GalleryQuery q) => _pageAt(q.offset, 10);

    final GalleryPage page = await load();

    expect(page.items, hasLength(2));
    expect(repo.pageQueries, <GalleryQuery>[const GalleryQuery()]);
    expect(repo.pageQueries.single.offset, 0);
    // R7a: default lens is Any state — no state filter is sent.
    expect(repo.pageQueries.single.state, '');
    expect(repo.pageQueries.single.used, 'all');
    expect(repo.pageQueries.single.limit, 60);
  });

  test('applyQuery replaces the lens and resets offset to 0', () async {
    repo.onFetchPage = (GalleryQuery q) => _pageAt(q.offset, 10);
    await load();

    await notifier().applyQuery(
      const GalleryQuery(search: 'fox', offset: 999),
    );

    expect(repo.pageQueries.last.offset, 0);
    expect(repo.pageQueries.last.search, 'fox');
    expect(state().items.first.id, 'r0');
    expect(container.read(galleryControllerProvider).hasValue, isTrue);
  });

  test('patchRecord swaps a row in place without a fetch', () async {
    repo.onFetchPage = (GalleryQuery q) => _pageAt(q.offset, 10);
    await load();
    final int fetches = repo.pageQueries.length;

    notifier().patchRecord(
      const ImageRecord(
        id: 'r0',
        filename: 'r0.jpg',
        status: 'PASSED',
        state: 'READY_TO_PUBLISH',
        flags: <String>['UNUSED'],
      ),
    );

    final ImageRecord patched = state().items.first;
    expect(patched.state, 'READY_TO_PUBLISH');
    expect(patched.used, isFalse);
    expect(state().total, 10); // totals untouched
    expect(repo.pageQueries, hasLength(fetches)); // zero network

    // An id outside the loaded window is a no-op, never a crash.
    notifier().patchRecord(
      const ImageRecord(id: 'ghost', filename: 'g.jpg', status: 'PENDING'),
    );
    expect(state().items.first.id, 'r0');
    expect(repo.pageQueries, hasLength(fetches));
  });

  test('loadMore appends until total and then stops asking', () async {
    repo.onFetchPage = (GalleryQuery q) => _pageAt(q.offset, 5);
    await load();

    await notifier().loadMore();
    await notifier().loadMore();

    expect(
      state().items.map<String>((ImageRecord r) => r.id).toList(),
      <String>['r0', 'r1', 'r2', 'r3', 'r4'],
    );
    expect(state().total, 5);

    await notifier().loadMore(); // full: no further request
    expect(
      repo.pageQueries.map<int>((GalleryQuery q) => q.offset).toList(),
      <int>[0, 2, 4],
    );
  });

  test('loadMore is a no-op while the first page is still loading', () async {
    repo.gate = Completer<void>();
    final Future<GalleryPage> pending = load();
    await pumpEventQueue();

    expect(container.read(galleryControllerProvider).isLoading, isTrue);
    await notifier().loadMore();
    expect(repo.pageQueries, hasLength(1));

    repo.gate!.complete();
    await pending;
  });

  test('an empty first page is an empty state, not an error', () async {
    repo.onFetchPage = (_) =>
        const GalleryPage(items: <ImageRecord>[], total: 0);

    final GalleryPage page = await load();

    expect(page.isEmpty, isTrue);
    expect(container.read(galleryControllerProvider).hasError, isFalse);
  });

  test('loadMore converges total when the server has nothing past the hold',
      () async {
    repo.onFetchPage = (GalleryQuery q) => q.offset >= 2
        ? const GalleryPage(items: <ImageRecord>[], total: 99)
        : _pageAt(q.offset, 99);
    await load();

    await notifier().loadMore();

    expect(state().items, hasLength(2));
    expect(state().total, 2); // promise dropped — the sentinel stops asking
    await notifier().loadMore();
    expect(repo.pageQueries, hasLength(2));
  });

  test('refresh keeps stale items on failure and rethrows', () async {
    repo.onFetchPage = (GalleryQuery q) => _pageAt(q.offset, 4);
    await load();
    repo.pageError = const ServerException(message: 'down');

    await expectLater(
      notifier().refresh(),
      throwsA(isA<ServerException>()),
    );

    final AsyncValue<GalleryPage> value =
        container.read(galleryControllerProvider);
    expect(value.hasValue, isTrue);
    expect(value.value!.items, hasLength(2)); // stale grid survives
  });

  test('refresh with nothing loaded lands as AsyncError', () async {
    repo.pageError = const ServerException(message: 'down');
    await expectLater(
      load(),
      throwsA(isA<ServerException>()),
    );

    await expectLater(
      notifier().refresh(),
      throwsA(isA<ServerException>()),
    );
    final AsyncValue<GalleryPage> value =
        container.read(galleryControllerProvider);
    expect(value.hasError, isTrue);
    expect(value.hasValue, isFalse);
  });

  test('a failed applyQuery reports through state, never throws', () async {
    repo.onFetchPage = (GalleryQuery q) => _pageAt(q.offset, 4);
    await load();
    repo.pageError = const ServerException(message: 'lens down');

    await notifier().applyQuery(const GalleryQuery(search: 'nothing'));

    final AsyncValue<GalleryPage> value =
        container.read(galleryControllerProvider);
    expect(value.hasError, isTrue);
    // Riverpod 3 keeps the previous page attached to the error — the spec
    // keeps stale items visible (the screen pairs them with the inline
    // ErrorView until the new lens resolves).
    expect(value.hasValue, isTrue);
    expect(value.value!.items, hasLength(2));
  });

  test('reloadAfterMutation refetches the whole loaded window', () async {
    repo.onFetchPage = (GalleryQuery q) {
      int count = q.limit;
      if (count > 8 - q.offset) {
        count = 8 - q.offset;
      }
      if (count < 0) {
        count = 0;
      }
      return GalleryPage(
        items: <ImageRecord>[
          for (int i = 0; i < count; i++) _record('r${q.offset + i}'),
        ],
        total: 8,
      );
    };

    await notifier().applyQuery(const GalleryQuery(limit: 2));
    expect(state().items, hasLength(2));
    await notifier().loadMore();
    expect(state().items, hasLength(4));

    await notifier().reloadAfterMutation();

    expect(repo.pageQueries.last.offset, 0);
    expect(repo.pageQueries.last.limit, 4); // window grew to the rows held
    expect(state().items, hasLength(4));
  });

  test('deleteRecords attempts every id, reloads, then rethrows', () async {
    repo.onFetchPage = (GalleryQuery q) => _pageAt(q.offset, 6);
    await load();
    repo.deleteErrors.add('b');

    await expectLater(
      notifier().deleteRecords(<String>['a', 'b', 'c']),
      throwsA(isA<ServerException>()),
    );

    expect(repo.deleteCalls, <String>['a', 'b', 'c']); // nobody skipped
    expect(repo.pageQueries, hasLength(2)); // the reload still ran
  });

  test('deleteRecords success reloads without throwing', () async {
    repo.onFetchPage = (GalleryQuery q) => _pageAt(q.offset, 6);
    await load();

    await notifier().deleteRecords(<String>['a']);

    expect(repo.deleteCalls, <String>['a']);
    expect(repo.pageQueries, hasLength(2));
    expect(container.read(galleryControllerProvider).hasError, isFalse);
  });

  test('markRecordsUsed loops single-record PATCHes in order', () async {
    repo.onFetchPage = (GalleryQuery q) => _pageAt(q.offset, 6);
    await load();

    await notifier().markRecordsUsed(<String>['x', 'y'], used: true);

    expect(
      repo.usedCalls,
      <({String id, bool used})>[
        (id: 'x', used: true),
        (id: 'y', used: true),
      ],
    );
    expect(repo.pageQueries, hasLength(2)); // flags reloaded into the window
  });

  test('downloadZip rejects empty and oversized selections before any IO',
      () async {
    await expectLater(
      notifier().downloadZip(const <String>[]),
      throwsA(isA<ValidationException>()),
    );
    await expectLater(
      notifier().downloadZip(
        List<String>.generate(
          GalleryController.maxZipFiles + 1,
          (int i) => 'id$i',
        ),
      ),
      throwsA(isA<ValidationException>()),
    );
  });
}
