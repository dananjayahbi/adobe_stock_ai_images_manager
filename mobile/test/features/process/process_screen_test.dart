import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:ai_stock_studio/app/theme/theme.dart';
import 'package:ai_stock_studio/core/utils/app_exception.dart';
import 'package:ai_stock_studio/core/widgets/connection_profile_banner.dart';
import 'package:ai_stock_studio/core/widgets/error_view.dart';
import 'package:ai_stock_studio/core/widgets/label_caps.dart';
import 'package:ai_stock_studio/features/process/domain/batch.dart';
import 'package:ai_stock_studio/features/process/domain/batch_step.dart';
import 'package:ai_stock_studio/features/process/domain/process_repository.dart';
import 'package:ai_stock_studio/features/process/presentation/process_screen.dart';
import 'package:ai_stock_studio/features/settings/data/profile_store.dart';

/// Scriptable list backend: only `fetchBatches` matters on this screen.
class _FakeProcessRepository implements ProcessRepository {
  BatchList list = const BatchList(items: <Batch>[], total: 0);
  Object? listError;
  int fetchCalls = 0;

  @override
  Future<BatchList> fetchBatches({int limit = 50}) async {
    fetchCalls += 1;
    final Object? error = listError;
    if (error != null) {
      throw error; // ignore: only_throw_errors — fake failure injection
    }
    return list;
  }

  @override
  Future<BatchDetail> fetchBatchDetail(String batchId) async =>
      throw UnimplementedError();

  @override
  Stream<BatchSnapshot> watchBatch(String batchId) =>
      throw UnimplementedError();

  @override
  Future<Batch> runBatch(String batchId) async => throw UnimplementedError();

  @override
  Future<StepCatalog> fetchStepCatalog({String? mediaType}) async =>
      throw UnimplementedError();

  @override
  Future<Batch> createBatch({
    required String name,
    required String mediaType,
    required List<BatchStep> steps,
    String? profileId,
  }) async => throw UnimplementedError();

  @override
  Future<Batch> cancelBatch(String batchId) async => throw UnimplementedError();

  @override
  Future<void> deleteBatch(String batchId) async => throw UnimplementedError();

  @override
  Future<List<StepProfile>> fetchProfiles({String? mediaType}) async =>
      throw UnimplementedError();

  @override
  Future<StepProfile> createProfile({
    required String name,
    required String mediaType,
    required List<BatchStep> steps,
  }) async => throw UnimplementedError();
}

Batch _batch({
  String id = 'b-1',
  String name = 'Alpha run',
  String status = 'completed',
  DateTime? createdAt,
  DateTime? updatedAt,
  DateTime? queuedAt,
}) => Batch(
  id: id,
  name: name,
  mediaType: 'raster',
  steps: const <BatchStep>[BatchStep(key: 'ocr')],
  profileId: null,
  status: status,
  stepProgress: null,
  error: null,
  recordCount: 4,
  createdAt: createdAt ?? DateTime(2026, 10, 13, 13, 38),
  updatedAt: updatedAt ?? DateTime(2026, 10, 13, 14, 2),
  finishedAt: null,
  queuedAt: queuedAt,
);

void main() {
  setUpAll(() {
    GoogleFonts.config.allowRuntimeFetching = false;
    SharedPreferences.setMockInitialValues({});
  });

  Future<void> pumpProcess(
    WidgetTester tester,
    _FakeProcessRepository repo,
  ) async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          processRepositoryProvider.overrideWithValue(repo),
          sharedPreferencesProvider.overrideWithValue(prefs),
        ],
        child: MaterialApp(theme: buildAppTheme(), home: const ProcessScreen()),
      ),
    );
  }

  /// Settles async provider work without waiting on infinite animations.
  Future<void> settle(WidgetTester tester) async {
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
  }

  /// Section titles render as [LabelCaps]; `PROCESSED` also prints on the
  /// stamps of completed cards, so headers are found scoped to LabelCaps.
  Finder sectionHeader(String title) => find.descendant(
    of: find.byType(LabelCaps),
    matching: find.text(title),
  );

  testWidgets('a failed pull-to-refresh keeps the stale rows and pins an '
      'inline retry (05 §3)', (WidgetTester tester) async {
    final _FakeProcessRepository repo = _FakeProcessRepository()
      ..list = BatchList(items: <Batch>[_batch()], total: 1);
    await pumpProcess(tester, repo);
    await settle(tester);
    expect(find.text('Alpha run'), findsOneWidget);
    expect(find.byType(ErrorView), findsNothing);

    // Server hiccup on refresh: rows stay, the failure surfaces inline.
    repo.listError = const ServerException(message: 'boom');
    await tester.fling(find.byType(ListView), const Offset(0, 300), 1000);
    await tester.pump(); // gesture starts
    await tester.pump(const Duration(seconds: 1)); // indicator snaps in
    await tester.pump(const Duration(seconds: 1)); // refresh fails
    await tester.pump(const Duration(seconds: 1)); // indicator exits
    await settle(tester);

    expect(find.byType(ErrorView), findsOneWidget);
    expect(find.text('Retry'), findsOneWidget);
    expect(find.text('Alpha run'), findsOneWidget); // stale row retained
    expect(
      find.text('The studio server hit an error. Please try again.'),
      findsOneWidget,
    );

    // Retry reconnects and clears the inline error.
    repo.listError = null;
    await tester.ensureVisible(find.text('Retry'));
    await tester.pump();
    await tester.tap(find.text('Retry'));
    await settle(tester);

    expect(find.byType(ErrorView), findsNothing);
    expect(find.text('Alpha run'), findsOneWidget);
    expect(repo.fetchCalls, 3); // load + failed refresh + retry
  });

  testWidgets(
    'orders per contract into ACTIVE/DRAFTS/PROCESSED/FINISHED with queue '
    'positions (#n)',
    (WidgetTester tester) async {
      // Tall viewport: every section row must exist for the ordering check.
      tester.view.physicalSize = const Size(1200, 2600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final _FakeProcessRepository repo = _FakeProcessRepository()
        ..list = BatchList(
          items: <Batch>[
            _batch(
              id: 'f-old',
              name: 'Old finish',
              status: 'completed',
              updatedAt: DateTime(2026, 10, 13, 10),
            ),
            _batch(
              id: 'd-2',
              name: 'Draft later',
              status: 'draft',
              updatedAt: DateTime(2026, 10, 16, 12),
            ),
            _batch(
              id: 'q-2',
              name: 'Queue second',
              status: 'queued',
              queuedAt: DateTime(2026, 10, 17, 8, 5),
            ),
            _batch(id: 'r-1', name: 'Running now', status: 'running'),
            _batch(
              id: 'd-1',
              name: 'Draft earlier',
              status: 'draft',
              updatedAt: DateTime(2026, 10, 15, 12),
            ),
            _batch(
              id: 'q-1',
              name: 'Queue first',
              status: 'queued',
              queuedAt: DateTime(2026, 10, 17, 8),
            ),
            _batch(
              id: 'f-new',
              name: 'New finish',
              status: 'completed',
              updatedAt: DateTime(2026, 10, 14, 10),
            ),
            _batch(
              id: 'x-1',
              name: 'Failed run',
              status: 'failed',
              updatedAt: DateTime(2026, 10, 12, 10),
            ),
            _batch(
              id: 'x-2',
              name: 'Cancelled run',
              status: 'cancelled',
              updatedAt: DateTime(2026, 10, 11, 10),
            ),
          ],
          total: 9,
        );
      await pumpProcess(tester, repo);
      await settle(tester);

      expect(sectionHeader('ACTIVE'), findsOneWidget);
      expect(sectionHeader('DRAFTS'), findsOneWidget);
      // 02 §1: completed is its own section — never lumped into FINISHED.
      expect(sectionHeader('PROCESSED'), findsOneWidget);
      expect(sectionHeader('FINISHED'), findsOneWidget);

      double y(Finder finder) => tester.getTopLeft(finder).dy;
      final double running = y(find.text('Running now'));
      final double queueFirst = y(find.text('Queue first'));
      final double queueSecond = y(find.text('Queue second'));
      final double draftLater = y(find.text('Draft later'));
      final double draftEarlier = y(find.text('Draft earlier'));
      final double finishNew = y(find.text('New finish'));
      final double finishOld = y(find.text('Old finish'));
      final double failedRun = y(find.text('Failed run'));
      final double cancelledRun = y(find.text('Cancelled run'));

      // running → queued (queued_at asc) → draft (updated desc) →
      // completed (updated desc) → failed/cancelled (updated desc).
      expect(running < queueFirst, isTrue);
      expect(queueFirst < queueSecond, isTrue);
      expect(queueSecond < draftLater, isTrue);
      expect(draftLater < draftEarlier, isTrue);
      expect(draftEarlier < finishNew, isTrue);
      expect(finishNew < finishOld, isTrue);
      expect(finishOld < failedRun, isTrue);
      expect(failedRun < cancelledRun, isTrue);

      // Queue position = index among queued + 1, in queue order.
      expect(find.text('#1'), findsOneWidget);
      expect(find.text('#2'), findsOneWidget);
      expect(y(find.text('#1')), lessThan(y(find.text('#2'))));

      // Section headers sit above their cards.
      expect(y(sectionHeader('ACTIVE')) < running, isTrue);
      expect(y(sectionHeader('DRAFTS')) < draftLater, isTrue);
      expect(y(sectionHeader('PROCESSED')) < finishNew, isTrue);
      expect(y(sectionHeader('FINISHED')) < failedRun, isTrue);

      // The screen owns a 2s poll while active — unmount so the timer dies.
      await tester.pumpWidget(const MaterialApp(home: SizedBox()));
      await tester.pump();
    },
  );

  testWidgets('a completed batch renders under Processed and never under '
      'Drafts (02 §1 regression)', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1200, 1400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final _FakeProcessRepository repo = _FakeProcessRepository()
      ..list = BatchList(
        items: <Batch>[
          _batch(
            id: 'd-1',
            name: 'Draft one',
            status: 'draft',
            updatedAt: DateTime(2026, 10, 16, 12),
          ),
          _batch(
            id: 'c-1',
            name: 'Batch done',
            status: 'completed',
            updatedAt: DateTime(2026, 10, 15, 12),
          ),
        ],
        total: 2,
      );
    await pumpProcess(tester, repo);
    await settle(tester);

    double y(Finder finder) => tester.getTopLeft(finder).dy;
    expect(sectionHeader('DRAFTS'), findsOneWidget);
    expect(sectionHeader('PROCESSED'), findsOneWidget);
    expect(sectionHeader('FINISHED'), findsNothing); // no failed/cancelled
    // The completed row sits under PROCESSED, below the Drafts block —
    // it can never render inside Drafts.
    expect(y(sectionHeader('DRAFTS')) < y(find.text('Draft one')), isTrue);
    expect(y(find.text('Draft one')) < y(sectionHeader('PROCESSED')), isTrue);
    expect(y(sectionHeader('PROCESSED')) < y(find.text('Batch done')), isTrue);

    // Completed-only list → the Drafts section doesn't even exist.
    final _FakeProcessRepository onlyDone = _FakeProcessRepository()
      ..list = BatchList(
        items: <Batch>[
          _batch(id: 'c-2', name: 'Solo run', status: 'completed'),
        ],
        total: 1,
      );
    await pumpProcess(tester, onlyDone);
    await settle(tester);
    expect(find.text('Solo run'), findsOneWidget);
    expect(sectionHeader('PROCESSED'), findsOneWidget);
    expect(sectionHeader('DRAFTS'), findsNothing);

    await tester.pumpWidget(const MaterialApp(home: SizedBox()));
    await tester.pump();
  });

  testWidgets('the list carries no connection-profile banner', (
    WidgetTester tester,
  ) async {
    final _FakeProcessRepository repo = _FakeProcessRepository()
      ..list = BatchList(items: <Batch>[_batch()], total: 1);
    await pumpProcess(tester, repo);
    await settle(tester);

    expect(find.byType(ConnectionProfileBanner), findsNothing);
  });

  testWidgets('polls the list every 2s while a batch is active and stops on '
      'dispose', (WidgetTester tester) async {
    final _FakeProcessRepository repo = _FakeProcessRepository()
      ..list = BatchList(
        items: <Batch>[
          _batch(id: 'r-1', name: 'Running now', status: 'running'),
        ],
        total: 1,
      );
    await pumpProcess(tester, repo);
    await settle(tester);
    expect(find.text('Running now'), findsOneWidget);

    final int before = repo.fetchCalls;
    await tester.pump(const Duration(seconds: 2));
    await tester.pump(const Duration(milliseconds: 100));
    expect(repo.fetchCalls, before + 1);

    await tester.pump(const Duration(seconds: 2));
    await tester.pump(const Duration(milliseconds: 100));
    expect(repo.fetchCalls, before + 2);

    // Leaving the screen cancels the loop (03 §4 lifecycle).
    await tester.pumpWidget(const MaterialApp(home: SizedBox()));
    await tester.pump();
    final int atDispose = repo.fetchCalls;
    await tester.pump(const Duration(seconds: 6));
    expect(repo.fetchCalls, atDispose);
  });
}
