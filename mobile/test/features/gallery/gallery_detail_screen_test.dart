import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:mocktail/mocktail.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:ai_stock_studio/app/theme/theme.dart';
import 'package:ai_stock_studio/core/utils/app_exception.dart';
import 'package:ai_stock_studio/core/utils/ui_message.dart';
import 'package:ai_stock_studio/features/gallery/domain/gallery_repository.dart';
import 'package:ai_stock_studio/features/gallery/domain/image_record.dart';
import 'package:ai_stock_studio/features/gallery/presentation/gallery_detail_screen.dart';
import 'package:ai_stock_studio/features/settings/data/profile_store.dart';

/// Mocktail fake — scriptable per method, tolerant of contract growth.
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
    // Never hit fonts.google.com from tests (03 §5).
    GoogleFonts.config.allowRuntimeFetching = false;
    SharedPreferences.setMockInitialValues(<String, Object>{});
    // HapticFeedback never completes under flutter_test without a
    // responder for SystemChannels.platform — ack every platform call so
    // the approve flow (haptic → approve → stamp) can proceed.
    TestWidgetsFlutterBinding.ensureInitialized();
    TestWidgetsFlutterBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, (call) async => null);
  });

  /// Pump the screen with the repository overridden; the controller is
  /// left untouched — AsyncLoading/error both fall back to the single
  /// record pager (05 §2.6).
  Future<void> pumpDetail(
    WidgetTester tester,
    FakeGalleryRepository repo, {
    String recordId = 'r1',
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
          home: GalleryDetailScreen(recordId: recordId),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
  }

  /// Settles async provider work without waiting on infinite animations.
  Future<void> settle(WidgetTester tester) async {
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
  }

  testWidgets('renders filename and metadata after load', (
    WidgetTester tester,
  ) async {
    final FakeGalleryRepository repo = FakeGalleryRepository();
    when(() => repo.fetchById('r1'))
        .thenAnswer((_) async => buildRecord());

    await pumpDetail(tester, repo);
    await settle(tester);

    // Chrome bar (page-local) shows the record filename.
    expect(find.text('wire_loop.jpg'), findsOneWidget);
    // Metadata sheet shows the generated title once loaded.
    expect(find.text('Wire loop sculpting tool'), findsOneWidget);
    // State stamps (chrome + sheet + over-image) render from `state` —
    // the legacy `PASSED` status rides along untouched underneath.
    expect(find.text('APPROVED'), findsWidgets);
    verify(() => repo.fetchById('r1')).called(1);
  });

  testWidgets('approve success stamps READY TO PUBLISH over the image, '
      'then clears', (WidgetTester tester) async {
    final FakeGalleryRepository repo = FakeGalleryRepository();
    when(() => repo.fetchById('r1')).thenAnswer((_) async => buildRecord());
    when(() => repo.approve('r1')).thenAnswer((_) async {});

    await pumpDetail(tester, repo);
    await settle(tester);

    await tester.tap(find.text('Approve'));
    await tester.pump(); // Microtasks: haptic → approve → toast + stamp.
    await tester.pump(const Duration(milliseconds: 400));

    // The approve contract flips APPROVED|REJECTED → READY_TO_PUBLISH, so
    // the transient stamp carries the resulting *state*.
    expect(find.text('READY TO PUBLISH'), findsWidgets);
    expect(find.text('Approved · wire_loop.jpg'), findsOneWidget);
    verify(() => repo.approve('r1')).called(1);

    // Stamp overlay auto-hides after ~1.2 s…
    await tester.pump(const Duration(milliseconds: 1300));
    expect(find.text('READY TO PUBLISH'), findsNothing);
    // …and the toast's 3 s timer is flushed so no timer dangles.
    await tester.pump(const Duration(seconds: 3));
    expect(find.text('Approved · wire_loop.jpg'), findsNothing);
  });

  testWidgets('approve NetworkException shows error toast, no stamp', (
    WidgetTester tester,
  ) async {
    final FakeGalleryRepository repo = FakeGalleryRepository();
    const NetworkException failure = NetworkException(message: 'no link');
    when(() => repo.fetchById('r1')).thenAnswer((_) async => buildRecord());
    when(() => repo.approve('r1')).thenThrow(failure);

    await pumpDetail(tester, repo);
    await settle(tester);

    await tester.tap(find.text('Approve'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    expect(find.text('READY TO PUBLISH'), findsNothing);
    expect(find.text(uiMessageFor(failure)), findsOneWidget);
    // The screen pinned itself offline: banner note + disabled actions.
    expect(
      find.textContaining('Offline — actions disabled'),
      findsOneWidget,
    );
    verify(() => repo.approve('r1')).called(1);

    await tester.pump(const Duration(seconds: 3)); // Flush toast timer.
    expect(find.text(uiMessageFor(failure)), findsNothing);
  });

  testWidgets('Approve is absent once the record is queued, published or '
      'accepted', (WidgetTester tester) async {
    final FakeGalleryRepository repo = FakeGalleryRepository();
    when(() => repo.approve('r1')).thenAnswer((_) async {});

    for (final String state in <String>[
      'READY_TO_PUBLISH',
      'PUBLISHED',
      'AS_ACCEPTED',
    ]) {
      when(() => repo.fetchById('r1'))
          .thenAnswer((_) async => buildRecord(state: state));
      await pumpDetail(tester, repo);
      await settle(tester);

      expect(find.text('Approve'), findsNothing, reason: state);
    }
    verifyNever(() => repo.approve('r1'));
  });

  testWidgets('menu shows Mark accepted only for PUBLISHED records', (
    WidgetTester tester,
  ) async {
    final FakeGalleryRepository repo = FakeGalleryRepository();
    when(() => repo.fetchById('r1'))
        .thenAnswer((_) async => buildRecord(state: 'PUBLISHED'));

    await pumpDetail(tester, repo);
    await settle(tester);

    await tester.tap(find.byTooltip('More actions'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Download'), findsOneWidget);
    expect(find.text('Mark accepted'), findsOneWidget);
    expect(find.text('Undo accepted'), findsNothing);
    await tester.tapAt(const Offset(400, 150)); // Dismiss the menu.
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
  });

  testWidgets('menu shows Undo accepted only for AS_ACCEPTED records', (
    WidgetTester tester,
  ) async {
    final FakeGalleryRepository repo = FakeGalleryRepository();
    when(() => repo.fetchById('r1'))
        .thenAnswer((_) async => buildRecord(state: 'AS_ACCEPTED'));

    await pumpDetail(tester, repo);
    await settle(tester);

    await tester.tap(find.byTooltip('More actions'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Download'), findsOneWidget);
    expect(find.text('Undo accepted'), findsOneWidget);
    expect(find.text('Mark accepted'), findsNothing);
    await tester.tapAt(const Offset(400, 150)); // Dismiss the menu.
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
  });
}
