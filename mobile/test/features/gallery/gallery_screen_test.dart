import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:ai_stock_studio/app/theme/theme.dart';
import 'package:ai_stock_studio/core/utils/app_exception.dart';
import 'package:ai_stock_studio/core/widgets/connection_profile_banner.dart';
import 'package:ai_stock_studio/core/widgets/error_view.dart';
import 'package:ai_stock_studio/core/widgets/skeleton_loader.dart';
import 'package:ai_stock_studio/features/gallery/domain/gallery_group.dart';
import 'package:ai_stock_studio/features/gallery/domain/gallery_page.dart';
import 'package:ai_stock_studio/features/gallery/domain/gallery_query.dart';
import 'package:ai_stock_studio/features/gallery/domain/gallery_repository.dart';
import 'package:ai_stock_studio/features/gallery/domain/image_record.dart';
import 'package:ai_stock_studio/features/gallery/presentation/filter_bar.dart';
import 'package:ai_stock_studio/features/gallery/presentation/gallery_screen.dart';
import 'package:ai_stock_studio/features/gallery/presentation/record_card.dart';
import 'package:ai_stock_studio/features/gallery/presentation/selection_toolbar.dart';
import 'package:ai_stock_studio/features/settings/data/profile_store.dart';

ImageRecord _record(String id, String filename) => ImageRecord(
      id: id,
      filename: filename,
      status: 'PASSED',
      thumbnailPath: '/tmp/$id.jpg',
    );

class _FakeGalleryRepository implements GalleryRepository {
  List<ImageRecord> items = <ImageRecord>[];
  int total = 0;
  List<GalleryGroup> groups = const <GalleryGroup>[];
  Object? pageError;
  final List<GalleryQuery> queries = <GalleryQuery>[];
  int pageCalls = 0;

  /// When set, every fetchPage awaits it — drives the skeleton test.
  Completer<void>? gate;

  @override
  Future<GalleryPage> fetchPage(GalleryQuery query) async {
    pageCalls += 1;
    queries.add(query);
    final Completer<void>? pending = gate;
    if (pending != null) {
      await pending.future;
    }
    if (pageError != null) {
      throw pageError!; // ignore: only_throw_errors — fake failure injection
    }
    return GalleryPage(items: items, total: total);
  }

  @override
  Future<List<GalleryGroup>> fetchGroups() async => groups;

  @override
  Future<ImageRecord> fetchById(String recordId) async => items.first;

  @override
  Future<void> approve(
    String recordId, {
    String? overrideTitle,
    String? overrideDescription,
    List<String>? overrideKeywords,
  }) async {}

  @override
  Future<void> markUsed(String recordId, {required bool used}) async {}

  @override
  Future<void> changeState(String recordId, String state) async {}

  @override
  Future<void> resetStage(String recordId) async {}

  @override
  Future<void> deleteRecord(String recordId) async {}
}

void main() {
  setUpAll(() {
    GoogleFonts.config.allowRuntimeFetching = false;
    SharedPreferences.setMockInitialValues({});
  });

  Future<void> pumpGallery(
    WidgetTester tester,
    _FakeGalleryRepository repo,
  ) async {
    final SharedPreferences storage = await SharedPreferences.getInstance();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          galleryRepositoryProvider.overrideWithValue(repo),
          sharedPreferencesProvider.overrideWithValue(storage),
        ],
        child: MaterialApp(
          theme: buildAppTheme(),
          home: const GalleryScreen(),
        ),
      ),
    );
  }

  /// Settles async provider work without waiting on infinite animations.
  Future<void> settle(WidgetTester tester) async {
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
  }

  _FakeGalleryRepository seededRepo() => _FakeGalleryRepository()
    ..items = <ImageRecord>[
      _record('r1', 'red_fox.jpg'),
      _record('r2', 'oak_table.jpg'),
      _record('r3', 'wire_loop.jpg'),
    ]
    ..total = 3;

  testWidgets('first load shows the 12-tile skeleton, then the grid', (
    WidgetTester tester,
  ) async {
    final _FakeGalleryRepository repo = seededRepo()..gate = Completer<void>();
    await pumpGallery(tester, repo);

    // Hero (local-only content) renders immediately; data tiles shimmer.
    expect(find.text('Gallery'), findsOneWidget); // shell up while loading
    expect(find.byType(SkeletonLoader), findsWidgets);
    expect(find.byType(RecordCard), findsNothing);
    expect(find.text('red_fox.jpg'), findsNothing);

    repo.gate!.complete();
    await settle(tester);

    // Tiles carry their own image placeholder, so pin the *grid* swap.
    expect(find.byType(RecordCard), findsNWidgets(3));
    expect(find.text('red_fox.jpg'), findsOneWidget);
    expect(find.text('oak_table.jpg'), findsOneWidget);
    expect(find.text('wire_loop.jpg'), findsOneWidget);
  });

  testWidgets('state chip tap swaps the lens from offset 0', (
    WidgetTester tester,
  ) async {
    final _FakeGalleryRepository repo = seededRepo();
    await pumpGallery(tester, repo);
    await settle(tester);
    expect(repo.queries, hasLength(1));

    await tester.ensureVisible(find.text('Collected'));
    await tester.pump();
    await tester.tap(find.text('Collected'));
    await settle(tester);

    expect(repo.queries.last.state, 'COLLECTED');
    expect(repo.queries.last.offset, 0);
    expect(repo.pageCalls, 2);
  });

  testWidgets('usage chip and debounced search rewrite the query', (
    WidgetTester tester,
  ) async {
    final _FakeGalleryRepository repo = seededRepo();
    await pumpGallery(tester, repo);
    await settle(tester);

    // The usage chips sit past the state strip — scroll them into view.
    final Finder chipList = find.descendant(
      of: find.byType(GalleryFilterBar),
      matching: find.byType(ListView),
    );
    // One far drag parks at the end of the strip where they live.
    await tester.drag(chipList, const Offset(-3200, 0));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    await tester.ensureVisible(find.text('Used'));
    await tester.pump();
    await tester.tap(find.text('Used'));
    await settle(tester);
    expect(repo.queries.last.used, 'used');

    // Debounce: nothing fires before 300 ms, then exactly one lens swap.
    final int callsBefore = repo.pageCalls;
    await tester.enterText(find.byType(TextField), 'fox');
    await tester.pump(const Duration(milliseconds: 100));
    expect(repo.pageCalls, callsBefore);

    await tester.pump(const Duration(milliseconds: 350));
    await settle(tester);
    expect(repo.queries.last.search, 'fox');
    expect(repo.pageCalls, callsBefore + 1);
  });

  testWidgets('filters that match nothing show the lens copy, not the '
      'empty-all CTA', (WidgetTester tester) async {
    final _FakeGalleryRepository repo = _FakeGalleryRepository()
      ..groups = <GalleryGroup>[
        const GalleryGroup(id: 'g1', name: 'wave 2', count: 30),
      ];
    await pumpGallery(tester, repo);
    await settle(tester);

    expect(find.text('Nothing matches this lens'), findsOneWidget);
    expect(find.text('The gallery is empty'), findsNothing);
  });

  testWidgets('a truly empty gallery offers the honest New batch toast', (
    WidgetTester tester,
  ) async {
    final _FakeGalleryRepository repo = _FakeGalleryRepository();
    await pumpGallery(tester, repo);
    await settle(tester);

    expect(find.text('The gallery is empty'), findsOneWidget);

    await tester.ensureVisible(find.text('New batch'));
    await tester.pump();
    await tester.tap(find.text('New batch'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 450));
    expect(find.text('Batch wizard arrives with M4'), findsOneWidget);
    expect(find.text('NOTICE'), findsOneWidget);
    await tester.pump(const Duration(seconds: 3)); // clear the pending timer
    expect(find.text('Batch wizard arrives with M4'), findsNothing);
  });

  testWidgets('page error keeps the shell (filters, title) and '
      'Retry refetches', (WidgetTester tester) async {
    final _FakeGalleryRepository repo = _FakeGalleryRepository()
      ..pageError = const ServerException(message: 'boom');
    await pumpGallery(tester, repo);
    await settle(tester);

    expect(find.byType(ErrorView), findsOneWidget);
    expect(find.text('Gallery'), findsOneWidget);
    expect(find.byType(TextField), findsOneWidget); // FilterBar survives
    expect(find.byType(RecordCard), findsNothing);
    expect(repo.pageCalls, 1);

    repo.pageError = null;
    repo.items = <ImageRecord>[_record('r9', 'retry.jpg')];
    repo.total = 1;
    await tester.ensureVisible(find.text('Retry'));
    await tester.pump();
    await tester.tap(find.text('Retry'));
    await settle(tester);

    expect(repo.pageCalls, 2);
    expect(find.text('retry.jpg'), findsOneWidget);
    expect(find.byType(ErrorView), findsNothing);
  });

  testWidgets('long-press arms selection: count + toolbar actions, cancel '
      'exits', (WidgetTester tester) async {
    final _FakeGalleryRepository repo = seededRepo();
    await pumpGallery(tester, repo);
    await settle(tester);

    await tester.longPress(find.byType(RecordCard).first);
    await tester.pump();

    expect(find.text('1 SELECTED'), findsOneWidget);
    expect(find.text('Download zip'), findsOneWidget);
    expect(find.text('Delete'), findsOneWidget);
    expect(find.text('Mark used'), findsOneWidget);

    // Toolbar floats as the inner bottom bar (above the shell's tab bar).
    expect(find.byType(SelectionToolbar), findsOneWidget);

    await tester.tap(find.byTooltip('Cancel selection'));
    await tester.pump();
    expect(find.text('1 SELECTED'), findsNothing);
    expect(find.byType(SelectionToolbar), findsNothing);
  });

  testWidgets('network failure while rows are stale dims the selection '
      'toolbar behind an offline caption (05 §3)', (WidgetTester tester) async {
    final _FakeGalleryRepository repo = seededRepo();
    await pumpGallery(tester, repo);
    await settle(tester);

    await tester.longPress(find.byType(RecordCard).first);
    await tester.pump();
    expect(find.byType(SelectionToolbar), findsOneWidget);

    // A pull-to-refresh that dies on the network keeps the stale grid and
    // marks the screen offline.
    repo.pageError = const NetworkException(message: 'link down');
    await tester.fling(
      find.byType(CustomScrollView),
      const Offset(0, 300),
      1000,
    );
    await tester.pump(); // gesture starts
    await tester.pump(const Duration(seconds: 1)); // indicator snaps in
    await tester.pump(const Duration(seconds: 1)); // refresh runs
    await tester.pump(const Duration(seconds: 1)); // indicator exits
    await settle(tester);

    expect(find.textContaining('Offline — actions disabled'), findsOneWidget);
    expect(find.byType(RecordCard), findsWidgets); // stale rows retained

    // Delete is inert while offline: the confirm dialog never opens.
    await tester.tap(find.text('Delete'), warnIfMissed: false);
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Delete 1 image?'), findsNothing);

    // Reconnecting clears the caption.
    repo.pageError = null;
    await tester.fling(
      find.byType(CustomScrollView),
      const Offset(0, 300),
      1000,
    );
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    await tester.pump(const Duration(seconds: 1));
    await tester.pump(const Duration(seconds: 1));
    await settle(tester);

    expect(find.textContaining('Offline — actions disabled'), findsNothing);
    expect(find.byType(SelectionToolbar), findsOneWidget);
  });

  testWidgets('header is two rows: full-width search above the chip strip, '
      'with no connection banner and compact folder cards', (
    WidgetTester tester,
  ) async {
    final _FakeGalleryRepository repo = seededRepo()
      ..groups = <GalleryGroup>[
        const GalleryGroup(id: 'g1', name: 'wave 2', count: 30),
      ];
    await pumpGallery(tester, repo);
    await settle(tester);

    // The gallery drops the banner other screens keep.
    expect(find.byType(ConnectionProfileBanner), findsNothing);

    // Row 1: the search field owns the full width (only the lg insets).
    final Size searchSize = tester.getSize(find.byType(TextField));
    expect(searchSize.width, greaterThan(700)); // 800 − 2×16 padding
    final double searchTop = tester.getTopLeft(find.byType(TextField)).dy;

    // Row 2: the chip strip sits beneath the search field.
    final Finder chipStrip = find.descendant(
      of: find.byType(GalleryFilterBar),
      matching: find.byType(ListView),
    );
    expect(chipStrip, findsOneWidget);
    expect(tester.getTopLeft(chipStrip).dy, greaterThan(searchTop));

    // Folder cards underneath are shrunk (140×56, was 176×72).
    final Size cardSize = tester.getSize(find.byType(GroupCard).first);
    expect(cardSize.width, 140);
    expect(cardSize.height, 56);
  });
}
