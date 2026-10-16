import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:mocktail/mocktail.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:ai_stock_studio/app/theme/theme.dart';
import 'package:ai_stock_studio/features/gallery/domain/gallery_repository.dart';
import 'package:ai_stock_studio/features/gallery/domain/image_record.dart';
import 'package:ai_stock_studio/features/gallery/presentation/review_action_bar.dart';
import 'package:ai_stock_studio/features/settings/data/profile_store.dart';

class FakeGalleryRepository extends Mock implements GalleryRepository {}

ImageRecord buildRecord({
  String id = 'r1',
  String status = 'PASSED',
  String state = 'APPROVED',
  bool? used = false,
}) {
  return ImageRecord(
    id: id,
    filename: 'wire_loop.jpg',
    status: status,
    state: state,
    thumbnailPath: null,
    used: used,
    generatedTitle: 'Wire loop sculpting tool',
    generatedDescription: 'A fine loop tool for shaping clay.',
    generatedKeywords: const <String>['wire loop', 'sculpting'],
    acceptanceScore: 0.91,
    width: 2048,
    height: 2048,
    fileSizeBytes: 255416,
  );
}

void main() {
  setUpAll(() {
    GoogleFonts.config.allowRuntimeFetching = false;
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  Future<void> pumpBar(
    WidgetTester tester, {
    required FakeGalleryRepository repo,
    ImageRecord? record,
    bool offline = false,
    VoidCallback? onApproved,
    VoidCallback? onRecordChanged,
    VoidCallback? onDeleted,
    ValueChanged<bool>? onConnectivityChanged,
  }) async {
    final SharedPreferences storage = await SharedPreferences.getInstance();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          galleryRepositoryProvider.overrideWithValue(repo),
          sharedPreferencesProvider.overrideWithValue(storage),
        ],
        child: MaterialApp(
          theme: buildAppTheme(),
          home: Scaffold(
            body: ReviewActionBar(
              record: record ?? buildRecord(),
              offline: offline,
              onApproved: onApproved ?? () {},
              onRecordChanged: onRecordChanged ?? () {},
              onDeleted: onDeleted ?? () {},
              onConnectivityChanged: onConnectivityChanged ?? (_) {},
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
  }

  Future<void> openMenu(WidgetTester tester, {bool warnIfMissed = true}) async {
    await tester.tap(find.byTooltip('More actions'), warnIfMissed: warnIfMissed);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
  }

  testWidgets('offline flag disables Approve and the overflow menu', (
    WidgetTester tester,
  ) async {
    final FakeGalleryRepository repo = FakeGalleryRepository();
    when(() => repo.approve('r1')).thenAnswer((_) async {});
    await pumpBar(tester, repo: repo, offline: true);

    expect(
      find.textContaining('Offline — actions disabled'),
      findsOneWidget,
    );

    // Both are deliberately blocked by IgnorePointer — silence the
    // hit-test warning (flutter_test's documented disabled-tap pattern).
    await tester.tap(find.text('Approve'), warnIfMissed: false);
    await tester.pump();
    verifyNever(() => repo.approve('r1'));

    await openMenu(tester, warnIfMissed: false);
    expect(find.text('Download'), findsNothing);
  });

  testWidgets('overflow opens the menu with all four actions', (
    WidgetTester tester,
  ) async {
    final FakeGalleryRepository repo = FakeGalleryRepository();
    await pumpBar(tester, repo: repo);

    await openMenu(tester);

    expect(find.text('Download'), findsOneWidget);
    expect(find.text('Mark used'), findsOneWidget);
    expect(find.text('Reset stage'), findsOneWidget);
    expect(find.text('Delete'), findsOneWidget);
    // Base state (APPROVED): no published⇄accepted pair in either
    // direction.
    expect(find.text('Mark accepted'), findsNothing);
    expect(find.text('Undo accepted'), findsNothing);
  });

  testWidgets('PUBLISHED menu gains Mark accepted, never Undo accepted', (
    WidgetTester tester,
  ) async {
    final FakeGalleryRepository repo = FakeGalleryRepository();
    await pumpBar(tester, repo: repo, record: buildRecord(state: 'PUBLISHED'));

    await openMenu(tester);

    expect(find.text('Download'), findsOneWidget);
    expect(find.text('Mark used'), findsOneWidget);
    expect(find.text('Mark accepted'), findsOneWidget);
    expect(find.text('Reset stage'), findsOneWidget);
    expect(find.text('Delete'), findsOneWidget);
    expect(find.text('Undo accepted'), findsNothing);
  });

  testWidgets('AS_ACCEPTED menu gains Undo accepted, never Mark accepted', (
    WidgetTester tester,
  ) async {
    final FakeGalleryRepository repo = FakeGalleryRepository();
    await pumpBar(
      tester,
      repo: repo,
      record: buildRecord(state: 'AS_ACCEPTED'),
    );

    await openMenu(tester);

    expect(find.text('Download'), findsOneWidget);
    expect(find.text('Mark used'), findsOneWidget);
    expect(find.text('Undo accepted'), findsOneWidget);
    expect(find.text('Reset stage'), findsOneWidget);
    expect(find.text('Delete'), findsOneWidget);
    expect(find.text('Mark accepted'), findsNothing);
  });

  testWidgets('Mark accepted PATCHes the state and reports back', (
    WidgetTester tester,
  ) async {
    final FakeGalleryRepository repo = FakeGalleryRepository();
    when(() => repo.changeState('r1', 'AS_ACCEPTED'))
        .thenAnswer((_) async {});
    bool changed = false;
    await pumpBar(
      tester,
      repo: repo,
      record: buildRecord(state: 'PUBLISHED'),
      onRecordChanged: () => changed = true,
    );

    await openMenu(tester);
    await tester.tap(find.text('Mark accepted'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    verify(() => repo.changeState('r1', 'AS_ACCEPTED')).called(1);
    expect(changed, isTrue);
    expect(find.text('Marked accepted · wire_loop.jpg'), findsOneWidget);

    await tester.pump(const Duration(seconds: 3)); // Flush toast timer.
    expect(find.text('Marked accepted · wire_loop.jpg'), findsNothing);
  });

  testWidgets('Undo accepted PATCHes back to PUBLISHED', (
    WidgetTester tester,
  ) async {
    final FakeGalleryRepository repo = FakeGalleryRepository();
    when(() => repo.changeState('r1', 'PUBLISHED')).thenAnswer((_) async {});
    bool changed = false;
    await pumpBar(
      tester,
      repo: repo,
      record: buildRecord(state: 'AS_ACCEPTED'),
      onRecordChanged: () => changed = true,
    );

    await openMenu(tester);
    await tester.tap(find.text('Undo accepted'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    verify(() => repo.changeState('r1', 'PUBLISHED')).called(1);
    expect(changed, isTrue);
    expect(find.text('Back to published · wire_loop.jpg'), findsOneWidget);

    await tester.pump(const Duration(seconds: 3)); // Flush toast timer.
    expect(find.text('Back to published · wire_loop.jpg'), findsNothing);
  });

  testWidgets('Approve renders only for APPROVED and REJECTED records', (
    WidgetTester tester,
  ) async {
    final FakeGalleryRepository repo = FakeGalleryRepository();

    for (final String state in <String>['APPROVED', 'REJECTED']) {
      await pumpBar(tester, repo: repo, record: buildRecord(state: state));
      expect(find.text('Approve'), findsOneWidget, reason: state);
    }
  });

  testWidgets('Approve is absent for every non-approvable state', (
    WidgetTester tester,
  ) async {
    final FakeGalleryRepository repo = FakeGalleryRepository();
    when(() => repo.approve('r1')).thenAnswer((_) async {});

    for (final String state in <String>[
      'COLLECTED',
      'READY_TO_PUBLISH',
      'PUBLISHED',
      'AS_ACCEPTED',
    ]) {
      await pumpBar(tester, repo: repo, record: buildRecord(state: state));
      expect(find.text('Approve'), findsNothing, reason: state);
    }
    verifyNever(() => repo.approve('r1'));
  });

  testWidgets('Delete asks for confirmation; Cancel deletes nothing', (
    WidgetTester tester,
  ) async {
    final FakeGalleryRepository repo = FakeGalleryRepository();
    when(() => repo.deleteRecord('r1')).thenAnswer((_) async {});
    bool deleted = false;
    await pumpBar(
      tester,
      repo: repo,
      onDeleted: () => deleted = true,
    );

    await openMenu(tester);
    await tester.tap(find.text('Delete'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Delete this record?'), findsOneWidget);

    await tester.tap(find.text('Cancel'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Delete this record?'), findsNothing);

    verifyNever(() => repo.deleteRecord('r1'));
    expect(deleted, isFalse);
  });

  testWidgets('Mark used calls the repository and reports back', (
    WidgetTester tester,
  ) async {
    final FakeGalleryRepository repo = FakeGalleryRepository();
    when(() => repo.markUsed('r1', used: true)).thenAnswer((_) async {});
    bool changed = false;
    await pumpBar(
      tester,
      repo: repo,
      onRecordChanged: () => changed = true,
    );

    await openMenu(tester);
    await tester.tap(find.text('Mark used'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    verify(() => repo.markUsed('r1', used: true)).called(1);
    expect(changed, isTrue);
    expect(find.text('Marked used · wire_loop.jpg'), findsOneWidget);

    await tester.pump(const Duration(seconds: 3)); // Flush toast timer.
    expect(find.text('Marked used · wire_loop.jpg'), findsNothing);
  });
}
