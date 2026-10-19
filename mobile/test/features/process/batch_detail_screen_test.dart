import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:ai_stock_studio/app/theme/theme.dart';
import 'package:ai_stock_studio/core/utils/app_exception.dart';
import 'package:ai_stock_studio/core/widgets/connection_profile_banner.dart';
import 'package:ai_stock_studio/features/process/domain/batch.dart';
import 'package:ai_stock_studio/features/process/domain/batch_step.dart';
import 'package:ai_stock_studio/features/process/domain/process_repository.dart';
import 'package:ai_stock_studio/features/process/presentation/batch_detail_screen.dart';
import 'package:ai_stock_studio/features/settings/data/profile_store.dart';

/// Configurable in-memory backend for the detail screen: canned detail,
/// a switchable watch stream, call counters for the polling assertions.
class _FakeProcessRepository implements ProcessRepository {
  BatchDetail? detail;
  Object? detailError;
  Object? runError;
  Stream<BatchSnapshot> watch = const Stream<BatchSnapshot>.empty();

  int detailCalls = 0;
  final List<String> runCalls = <String>[];

  @override
  Future<BatchDetail> fetchBatchDetail(String batchId) async {
    detailCalls++;
    final Object? error = detailError;
    if (error != null) {
      throw error;
    }
    return detail!;
  }

  @override
  Stream<BatchSnapshot> watchBatch(String batchId) => watch;

  @override
  Future<Batch> runBatch(String batchId) async {
    runCalls.add(batchId);
    final Object? error = runError;
    if (error != null) {
      throw error;
    }
    return detail!;
  }

  @override
  Future<StepCatalog> fetchStepCatalog({String? mediaType}) async =>
      const StepCatalog(
        order: <String>['ocr', 'metadata'],
        steps: <StepDefinition>[
          StepDefinition(
            key: 'ocr',
            label: 'OCR text',
            description: 'Read visible text.',
            mediaTypes: <String>['raster', 'png'],
            defaultConfig: <String, Object?>{},
          ),
          StepDefinition(
            key: 'metadata',
            label: 'Metadata & CSV',
            description: 'Fill the listing fields.',
            mediaTypes: <String>['raster', 'png'],
            defaultConfig: <String, Object?>{},
          ),
        ],
      );

  @override
  Future<BatchList> fetchBatches({int limit = 50}) async =>
      throw UnimplementedError();

  @override
  Future<Batch> createBatch({
    required String name,
    required String mediaType,
    required List<BatchStep> steps,
    String? profileId,
  }) async =>
      throw UnimplementedError();

  @override
  Future<Batch> cancelBatch(String batchId) async => detail!;

  Object? deleteError;
  final List<String> deleteCalls = <String>[];

  @override
  Future<void> deleteBatch(String batchId) async {
    deleteCalls.add(batchId);
    final Object? error = deleteError;
    if (error != null) {
      throw error; // ignore: only_throw_errors — fake failure injection
    }
  }

  @override
  Future<List<StepProfile>> fetchProfiles({String? mediaType}) async =>
      throw UnimplementedError();

  @override
  Future<StepProfile> createProfile({
    required String name,
    required String mediaType,
    required List<BatchStep> steps,
  }) async =>
      throw UnimplementedError();
}

BatchDetail _detail({
  String status = 'running',
  Map<String, StepProgress>? stepProgress,
}) =>
    BatchDetail(
      id: 'b-1',
      name: 'Raster run',
      mediaType: 'raster',
      steps: const <BatchStep>[
        BatchStep(key: 'ocr'),
        BatchStep(key: 'metadata'),
      ],
      profileId: null,
      status: status,
      stepProgress: stepProgress,
      error: null,
      recordCount: 4,
      createdAt: DateTime(2026, 10, 13, 13, 38),
      updatedAt: DateTime(2026, 10, 13, 14, 2),
      finishedAt: null,
      records: const <BatchRecord>[],
    );

void main() {
  setUpAll(() {
    GoogleFonts.config.allowRuntimeFetching = false;
    SharedPreferences.setMockInitialValues({});
    TestWidgetsFlutterBinding.ensureInitialized();
    // Haptics never complete under flutter_test without a responder.
    TestWidgetsFlutterBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
      SystemChannels.platform,
      (MethodCall call) async => null,
    );
  });

  Future<void> pumpDetail(
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
        child: MaterialApp(
          theme: buildAppTheme(),
          home: const BatchDetailScreen(batchId: 'b-1'),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
  }

  testWidgets('renders the step timeline with catalog labels and per-step '
      'results, then flips to LIVE on a snapshot', (WidgetTester tester) async {
    final _FakeProcessRepository repo = _FakeProcessRepository()
      ..detail = _detail(
        status: 'running',
        stepProgress: <String, StepProgress>{
          'ocr': const StepProgress(
            status: 'completed',
            message: '28 ok · 1 failed',
            counts: <String, int>{
              'succeeded': 28,
              'failed': 1,
              'skipped': 0,
              'pending': 0,
            },
          ),
          'metadata': const StepProgress(status: 'pending', message: ''),
        },
      );
    final StreamController<BatchSnapshot> live =
        StreamController<BatchSnapshot>();
    repo.watch = live.stream;

    await pumpDetail(tester, repo);

    expect(find.text('Raster run'), findsOneWidget);
    expect(find.text('LIVE'), findsNothing); // nothing streamed yet
    // Steps from the batch payload, labelled via the step catalog.
    expect(find.text('OCR text'), findsOneWidget);
    expect(find.text('Metadata & CSV'), findsOneWidget);
    expect(find.text('28 ok · 1 failed'), findsOneWidget); // per-image line
    expect(find.text('completed'), findsWidgets); // per-step status chips

    live.add(
      BatchSnapshot(
        _detail(
          status: 'running',
          stepProgress: <String, StepProgress>{
            'ocr': const StepProgress(
              status: 'running',
              message: '3 ok · 2 pending',
              counts: <String, int>{
                'succeeded': 3,
                'failed': 0,
                'skipped': 0,
                'pending': 2,
              },
            ),
            'metadata': const StepProgress(status: 'pending', message: ''),
          },
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.text('LIVE'), findsOneWidget); // SSE flowing (05 §2.7.2)
    expect(find.text('3 ok · 2 pending'), findsOneWidget);
    expect(find.text('POLLING'), findsNothing);
  });

  testWidgets('stream failure falls back to 2.5s polling and polling stops '
      'after dispose', (WidgetTester tester) async {
    final _FakeProcessRepository repo = _FakeProcessRepository()
      ..detail = _detail(status: 'running')
      ..watch = Stream<BatchSnapshot>.error(NetworkException(message: 'cut'));

    await pumpDetail(tester, repo);

    expect(find.text('POLLING'), findsOneWidget); // fallback chip (05 §2.7.2)
    expect(find.text('LIVE'), findsNothing);
    // Detail provider's first fetch + the immediate fallback poll.
    final int callsAtStart = repo.detailCalls;
    expect(callsAtStart, greaterThanOrEqualTo(2));

    await tester.pump(const Duration(milliseconds: 2500));
    expect(repo.detailCalls, greaterThan(callsAtStart)); // periodic tick ran

    // Leaving the screen must stop the loop (03 §4 lifecycle).
    await tester.pumpWidget(const MaterialApp(home: SizedBox()));
    await tester.pump();
    final int callsAtDispose = repo.detailCalls;
    await tester.pump(const Duration(seconds: 5));
    expect(repo.detailCalls, callsAtDispose);
  });

  testWidgets('404 after a studio restart shows the friendly error copy',
      (WidgetTester tester) async {
    final _FakeProcessRepository repo = _FakeProcessRepository()
      ..detailError = NotFoundException(message: 'gone')
      ..watch = Stream<BatchSnapshot>.error(NotFoundException(message: 'gone'));

    await pumpDetail(tester, repo);
    await tester.pump(const Duration(milliseconds: 100));

    expect(
      find.text('Batch info no longer available (studio restarted)'),
      findsOneWidget,
    );
    expect(find.text('Back to batches'), findsOneWidget);
  });

  testWidgets('Run batch asks for confirmation before posting', (
    WidgetTester tester,
  ) async {
    final _FakeProcessRepository repo = _FakeProcessRepository()
      ..detail = _detail(status: 'draft');

    await pumpDetail(tester, repo);

    expect(find.text('Run batch'), findsOneWidget);
    await tester.tap(find.text('Run batch'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.text('Run batch?'), findsOneWidget); // confirm dialog
    expect(repo.runCalls, isEmpty); // not posted yet

    await tester.tap(find.text('Run'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(repo.runCalls, <String>['b-1']);
    expect(find.text('Batch started'), findsOneWidget); // success toast

    // Let the toast timer (3 s) and any fallback poll ticks fire so the
    // test never ends on a pending timer; teardown then disposes the tree.
    await tester.pump(const Duration(seconds: 3));
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('Batch started'), findsNothing);
  });

  testWidgets('Run batch network failure pins the offline note and dims '
      'Run/Stop until the re-probe succeeds (05 §3)', (WidgetTester tester) async {
    final _FakeProcessRepository repo = _FakeProcessRepository()
      ..detail = _detail(status: 'draft');

    await pumpDetail(tester, repo);
    expect(find.text('Run batch'), findsOneWidget);

    // Action and follow-up re-probe both die on the network.
    repo.runError = const NetworkException(message: 'link down');
    repo.detailError = const NetworkException(message: 'link down');
    await tester.tap(find.text('Run batch'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    await tester.tap(find.text('Run'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump(const Duration(milliseconds: 100));

    // Stale payload stays up; the caption explains the parked actions.
    expect(find.text('Raster run'), findsOneWidget);
    expect(find.textContaining('Offline — actions disabled'), findsOneWidget);

    // Dimmed Run is inert: no confirm dialog opens.
    await tester.tap(find.text('Run batch'), warnIfMissed: false);
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Run batch?'), findsNothing);

    // A successful pull-to-refresh re-probe clears the offline note.
    repo.runError = null;
    repo.detailError = null;
    await tester.fling(
      find.byType(ListView),
      const Offset(0, 300),
      1000,
    );
    await tester.pump(); // gesture starts
    await tester.pump(const Duration(seconds: 1)); // indicator snaps in
    await tester.pump(const Duration(seconds: 1)); // re-probe runs
    await tester.pump(const Duration(seconds: 1)); // indicator exits
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.textContaining('Offline — actions disabled'), findsNothing);
    expect(find.text('Raster run'), findsOneWidget);

    // Flush the network-error toast timer so no timer dangles.
    await tester.pump(const Duration(seconds: 3));
    await tester.pump(const Duration(milliseconds: 100));
  });

  testWidgets('action matrix: completed → processed note + Delete (no Run), '
      'draft/failed/cancelled → Run + Delete, running/queued → Stop only '
      '(02 §1)', (WidgetTester tester) async {
    final _FakeProcessRepository repo = _FakeProcessRepository();

    Future<void> pumpStatus(String status) async {
      // Full unmount between statuses so each pump gets a fresh container
      // (the detail + events providers cache per scope).
      await tester.pumpWidget(const SizedBox());
      await tester.pump();
      repo.detail = _detail(status: status);
      await pumpDetail(tester, repo);
    }

    await pumpStatus('completed');
    expect(find.text('PROCESSED'), findsOneWidget); // header stamp
    expect(
      find.text('Processed — delete to run a fresh batch'),
      findsOneWidget,
    );
    expect(find.text('Run batch'), findsNothing);
    expect(find.text('Stop'), findsNothing);
    expect(find.text('Delete'), findsOneWidget);

    for (final String status in <String>['draft', 'failed', 'cancelled']) {
      await pumpStatus(status);
      expect(find.text('Run batch'), findsOneWidget);
      expect(find.text('Delete'), findsOneWidget);
      expect(find.text('Stop'), findsNothing);
      expect(find.textContaining('delete to run a fresh batch'), findsNothing);
      expect(repo.runCalls, isEmpty); // gated behind a confirm dialog
      expect(repo.deleteCalls, isEmpty);
    }

    for (final String status in <String>['running', 'queued']) {
      await pumpStatus(status);
      expect(find.text('Stop'), findsOneWidget);
      expect(find.text('Run batch'), findsNothing);
      expect(find.text('Delete'), findsNothing); // backend would 409
    }

    await tester.pumpWidget(const SizedBox());
    await tester.pump();
  });

  testWidgets('Delete asks for confirmation with name + count, posts, toasts '
      'and returns to /process', (WidgetTester tester) async {
    final _FakeProcessRepository repo = _FakeProcessRepository()
      ..detail = _detail(status: 'completed');
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    final GoRouter router = GoRouter(
      initialLocation: '/process/b-1',
      routes: <RouteBase>[
        GoRoute(
          path: '/process',
          builder: (BuildContext context, GoRouterState state) =>
              const Text('PROCESS LIST'),
        ),
        GoRoute(
          path: '/process/:batchId',
          builder: (BuildContext context, GoRouterState state) =>
              BatchDetailScreen(batchId: state.pathParameters['batchId']!),
        ),
      ],
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          processRepositoryProvider.overrideWithValue(repo),
          sharedPreferencesProvider.overrideWithValue(prefs),
        ],
        child: MaterialApp.router(
          theme: buildAppTheme(),
          routerConfig: router,
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    await tester.tap(find.text('Delete'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    // Confirm carries the name and the record_count sentence (02 §1).
    expect(find.text('Delete batch?'), findsOneWidget);
    expect(
      find.descendant(
        of: find.byType(AlertDialog),
        matching: find.textContaining('Raster run'),
      ),
      findsOneWidget,
    );
    expect(
      find.textContaining('4 images will be deleted with it'),
      findsOneWidget,
    );
    expect(repo.deleteCalls, isEmpty); // not posted yet

    await tester.tap(find.widgetWithText(TextButton, 'Delete'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump(const Duration(milliseconds: 300)); // route transition

    expect(repo.deleteCalls, <String>['b-1']);
    expect(
      find.text('Batch deleted · 4 images cleaned'),
      findsOneWidget,
    ); // success toast
    expect(find.text('PROCESS LIST'), findsOneWidget); // context.go
    expect(find.text('Raster run'), findsNothing); // detail gone

    // Flush the toast timer (3 s) so no timer dangles.
    await tester.pump(const Duration(seconds: 3));
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('Batch deleted · 4 images cleaned'), findsNothing);
  });

  testWidgets('delete 409 surfaces the backend detail verbatim in an error '
      'toast', (WidgetTester tester) async {
    final _FakeProcessRepository repo = _FakeProcessRepository()
      ..detail = _detail(status: 'completed')
      ..deleteError = const ServerException(
        message: 'already processed — delete it to start a fresh',
      );
    await pumpDetail(tester, repo);

    await tester.tap(find.text('Delete'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    await tester.tap(find.widgetWithText(TextButton, 'Delete'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump(const Duration(milliseconds: 100));

    expect(repo.deleteCalls, <String>['b-1']);
    expect(
      find.text('already processed — delete it to start a fresh'),
      findsOneWidget,
    );
    expect(find.text('Raster run'), findsOneWidget); // stayed on the screen

    await tester.pump(const Duration(seconds: 3));
    await tester.pump(const Duration(milliseconds: 100));
  });

  testWidgets('the detail screen carries no connection-profile banner', (
    WidgetTester tester,
  ) async {
    final _FakeProcessRepository repo = _FakeProcessRepository()
      ..detail = _detail(status: 'completed');
    await pumpDetail(tester, repo);

    expect(find.byType(ConnectionProfileBanner), findsNothing);
  });
}
