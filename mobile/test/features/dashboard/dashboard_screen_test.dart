import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:ai_stock_studio/app/theme/theme.dart';
import 'package:ai_stock_studio/core/utils/app_exception.dart';
import 'package:ai_stock_studio/core/widgets/error_view.dart';
import 'package:ai_stock_studio/core/widgets/live_dot.dart';
import 'package:ai_stock_studio/core/widgets/progress_bar.dart';
import 'package:ai_stock_studio/core/widgets/skeleton_loader.dart';
import 'package:ai_stock_studio/features/dashboard/data/dashboard_repository_impl.dart';
import 'package:ai_stock_studio/features/dashboard/domain/dashboard_repository.dart';
import 'package:ai_stock_studio/features/dashboard/domain/dashboard_stats.dart';
import 'package:ai_stock_studio/features/dashboard/presentation/dashboard_screen.dart';
import 'package:ai_stock_studio/features/settings/data/profile_store.dart';

/// Fake backend: every endpoint independently scriptable — the per-card
/// failure matrix (05 §2.4) is the point of these tests. The repository
/// provider is overridden directly, so Dio is never involved.
class FakeDashboardRepository implements DashboardRepository {
  StagesSummary stagesValue = const StagesSummary(
    counts: <StageCount>[],
    total: 161,
    ready: 12,
    rejected: 0,
    incompatible: 0,
    averageScore: 0.882,
  );
  QueuesSummary queuesValue = const QueuesSummary(
    counts: <String, int>{'metadata': 3},
    total: 3,
  );
  List<JobSummary> jobsValue = <JobSummary>[
    const JobSummary(
      id: 'j1',
      stage: 'metadata',
      kind: 'metadata-run',
      status: 'running',
      message: '',
      progressLabel: '',
      total: 12,
      processed: 3,
      succeeded: 3,
      failed: 0,
      skipped: 0,
      progress: 0.25,
    ),
  ];
  List<LatestImage> latestValue = <LatestImage>[
    const LatestImage(
      id: 'r1',
      filename: 'wire_loop.jpg',
      stage: 'METADATA_READY',
      title: 'Wire loop sculpting tool',
    ),
    const LatestImage(
      id: 'r2',
      filename: 'oak_table.jpg',
      stage: 'METADATA_READY',
      title: 'Oak table on white',
    ),
  ];

  Object? stagesError;
  Object? queuesError;
  Object? jobsError;
  Object? latestError;

  /// When set, every fetch awaits it — drives the loading-state test.
  Completer<void>? gate;

  int stagesCalls = 0;
  int queuesCalls = 0;
  int jobsCalls = 0;
  int latestCalls = 0;

  Future<T> _run<T>(Future<T> Function() body, Object? error) async {
    final Completer<void>? pending = gate;
    if (pending != null) {
      await pending.future;
    }
    if (error != null) {
      throw error; // ignore: only_throw_errors — fake failure injection
    }
    return body();
  }

  @override
  Future<StagesSummary> fetchStagesSummary(String platformId) {
    stagesCalls += 1;
    return _run(() async => stagesValue, stagesError);
  }

  @override
  Future<QueuesSummary> fetchQueuesSummary(String platformId) {
    queuesCalls += 1;
    return _run(() async => queuesValue, queuesError);
  }

  @override
  Future<List<JobSummary>> fetchJobs(String platformId, {int limit = 10}) {
    jobsCalls += 1;
    return _run(() async => jobsValue, jobsError);
  }

  @override
  Future<List<LatestImage>> fetchLatest(String platformId, {int limit = 8}) {
    latestCalls += 1;
    return _run(() async => latestValue, latestError);
  }
}

void main() {
  setUpAll(() {
    // Never hit fonts.google.com from tests (03 §5).
    GoogleFonts.config.allowRuntimeFetching = false;
    SharedPreferences.setMockInitialValues({});
  });

  Future<SharedPreferences> prefs() => SharedPreferences.getInstance();

  Future<void> pumpDashboard(
    WidgetTester tester,
    FakeDashboardRepository repo,
  ) async {
    final SharedPreferences storage = await prefs();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          dashboardRepositoryProvider.overrideWithValue(repo),
          sharedPreferencesProvider.overrideWithValue(storage),
        ],
        child: MaterialApp(
          theme: buildAppTheme(),
          home: const DashboardScreen(),
        ),
      ),
    );
  }

  /// Settles async provider work without waiting on infinite animations.
  Future<void> settle(WidgetTester tester) async {
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
  }

  testWidgets('loading shows hero plus per-card skeletons, then data', (
    WidgetTester tester,
  ) async {
    final FakeDashboardRepository repo = FakeDashboardRepository()
      ..gate = Completer<void>();
    await pumpDashboard(tester, repo);

    // Hero (local-only content) renders immediately; data cards shimmer.
    expect(find.text('A LOCAL PIPELINE FOR ADOBE STOCK'), findsOneWidget);
    expect(find.byType(SkeletonLoader), findsWidgets);
    expect(find.text('161'), findsNothing);

    repo.gate!.complete();
    await settle(tester);

    expect(find.byType(SkeletonLoader), findsNothing);
    expect(find.text('161'), findsOneWidget);
    expect(find.text('12'), findsOneWidget);
    expect(find.text('3'), findsOneWidget);
    expect(find.text('1'), findsOneWidget); // running jobs count
  });

  testWidgets('records endpoint failing: hero survives, Latest shows inline '
      'ErrorView, retry hits only that endpoint', (WidgetTester tester) async {
    final FakeDashboardRepository repo = FakeDashboardRepository()
      ..latestError = const NetworkException(message: 'down');
    await pumpDashboard(tester, repo);
    await settle(tester);

    // Shell + healthy cards untouched by the broken endpoint.
    expect(find.text('A LOCAL PIPELINE FOR ADOBE STOCK'), findsOneWidget);
    expect(find.text('161'), findsOneWidget);
    expect(find.text('3'), findsOneWidget);
    expect(find.byType(ErrorView), findsOneWidget);
    expect(
      find.text(
        "Can't reach the studio server. Check your network and connection profile.",
      ),
      findsOneWidget,
    );

    await tester.ensureVisible(find.text('Retry'));
    await tester.pump();
    await tester.tap(find.text('Retry'));
    await settle(tester);

    expect(repo.latestCalls, 2);
    expect(repo.stagesCalls, 1); // untouched
    expect(find.byType(ErrorView), findsOneWidget);
    expect(find.text('161'), findsOneWidget);
  });

  testWidgets('stages endpoint failing: its four stat cells error, the '
      'other cells keep live values', (WidgetTester tester) async {
    final FakeDashboardRepository repo = FakeDashboardRepository()
      ..stagesError = const ServerException(message: 'boom');
    await pumpDashboard(tester, repo);
    await settle(tester);

    expect(find.byType(ErrorView), findsNWidgets(4)); // records/ready/
    // approved/rejected cells — every stages-backed tile errors together.
    expect(find.text('3'), findsOneWidget); // queue depth survives
    expect(find.text('1'), findsOneWidget); // running jobs survives
    expect(find.text('161'), findsNothing);
  });

  testWidgets('state_counts drives the three state tiles when present', (
    WidgetTester tester,
  ) async {
    final FakeDashboardRepository repo = FakeDashboardRepository()
      ..stagesValue = const StagesSummary(
        counts: <StageCount>[],
        total: 30,
        ready: 7, // legacy fields must NOT win once state_counts ships
        rejected: 9,
        incompatible: 0,
        stateCounts: <String, int>{
          'READY_TO_PUBLISH': 4,
          'APPROVED': 5,
          'REJECTED': 6,
        },
      );
    await pumpDashboard(tester, repo);
    await settle(tester);

    expect(find.text('30'), findsOneWidget); // records total
    expect(find.text('4'), findsOneWidget); // Ready to publish
    expect(find.text('5'), findsOneWidget); // Approved
    expect(find.text('6'), findsOneWidget); // Rejected
    expect(find.text('7'), findsNothing); // legacy ready ignored
    expect(find.text('9'), findsNothing); // legacy rejected ignored
  });

  testWidgets('empty records show the batch CTA EmptyState', (
    WidgetTester tester,
  ) async {
    final FakeDashboardRepository repo = FakeDashboardRepository()
      ..latestValue = <LatestImage>[];
    await pumpDashboard(tester, repo);
    await settle(tester);

    expect(find.text('No images yet — start a batch'), findsOneWidget);
    expect(find.text('161'), findsOneWidget); // stats still live
  });

  testWidgets('success: running-job card + hero actions', (
    WidgetTester tester,
  ) async {
    final FakeDashboardRepository repo = FakeDashboardRepository();
    await pumpDashboard(tester, repo);
    await settle(tester);

    expect(find.text('161'), findsOneWidget);
    expect(find.text('12'), findsOneWidget);
    expect(find.text('3'), findsOneWidget);
    expect(find.text('1'), findsOneWidget);

    // Running-job card: name + LIVE dot + RUNNING caps + progress bar.
    expect(find.byType(LiveDot), findsOneWidget);
    expect(find.byType(ProgressBar), findsOneWidget);
    expect(find.text('RUNNING'), findsOneWidget);
    expect(find.text('metadata-run'), findsOneWidget);

    // Latest tiles link to the honest M3 toast (tiles carry their title as
    // the semantics label — the visual tile is image-only).
    final SemanticsHandle semantics = tester.ensureSemantics();
    expect(find.bySemanticsLabel('Wire loop sculpting tool'), findsOneWidget);
    expect(find.bySemanticsLabel('Oak table on white'), findsOneWidget);
    await tester.ensureVisible(find.bySemanticsLabel('Wire loop sculpting tool'));
    await tester.pump();
    await tester.tap(find.bySemanticsLabel('Wire loop sculpting tool'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 450));
    expect(find.text('Detail arrives with M3'), findsOneWidget);
    await tester.pump(const Duration(seconds: 3)); // let the toast timer fire
    semantics.dispose();

    // New batch stays visible with an honest M4 toast (no dead nav).
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
}
