import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:ai_stock_studio/app/router.dart';
import 'package:ai_stock_studio/app/error_screen.dart';
import 'package:ai_stock_studio/app/shell.dart';
import 'package:ai_stock_studio/app/splash_screen.dart';
import 'package:ai_stock_studio/app/tab_placeholder.dart';
import 'package:ai_stock_studio/app/theme/theme.dart';
import 'package:ai_stock_studio/features/auth/presentation/auth_controller.dart';
import 'package:ai_stock_studio/features/auth/presentation/login_screen.dart';
import 'package:ai_stock_studio/features/delivery/presentation/delivery_screen.dart';
import 'package:ai_stock_studio/features/gallery/domain/gallery_group.dart';
import 'package:ai_stock_studio/features/gallery/domain/gallery_page.dart';
import 'package:ai_stock_studio/features/gallery/domain/gallery_query.dart';
import 'package:ai_stock_studio/features/gallery/domain/gallery_repository.dart';
import 'package:ai_stock_studio/features/gallery/domain/image_record.dart';
import 'package:ai_stock_studio/features/gallery/presentation/gallery_detail_screen.dart';
import 'package:ai_stock_studio/features/gallery/presentation/gallery_screen.dart';
import 'package:ai_stock_studio/features/platforms/data/platform_repository_impl.dart';
import 'package:ai_stock_studio/features/platforms/domain/platform.dart';
import 'package:ai_stock_studio/features/platforms/domain/platform_repository.dart';
import 'package:ai_stock_studio/features/platforms/presentation/platform_hub_screen.dart';
import 'package:ai_stock_studio/features/process/domain/batch.dart';
import 'package:ai_stock_studio/features/process/domain/batch_step.dart';
import 'package:ai_stock_studio/features/process/domain/process_repository.dart';
import 'package:ai_stock_studio/features/process/presentation/batch_detail_screen.dart';
import 'package:ai_stock_studio/features/process/presentation/new_batch_screen.dart';
import 'package:ai_stock_studio/features/process/presentation/process_screen.dart';
import 'package:ai_stock_studio/features/queue/presentation/queue_indicator_bar.dart';
import 'package:ai_stock_studio/features/queue/presentation/queue_screen.dart';
import 'package:ai_stock_studio/features/settings/data/health_api.dart';
import 'package:ai_stock_studio/features/settings/data/profile_store.dart';
import 'package:ai_stock_studio/features/settings/domain/settings_repository.dart';
import 'package:ai_stock_studio/features/settings/presentation/about_screen.dart';
import 'package:ai_stock_studio/features/settings/presentation/account_screen.dart';
import 'package:ai_stock_studio/features/settings/presentation/connection_editor_screen.dart';
import 'package:ai_stock_studio/features/settings/presentation/connections_screen.dart';
import 'package:ai_stock_studio/features/settings/presentation/settings_screen.dart';

/// In-memory catalogue so the hub never touches the network in tests.
class _FakePlatformRepository implements PlatformRepository {
  @override
  Future<List<PlatformEntry>> fetchPlatforms() async => const <PlatformEntry>[
        PlatformEntry(
          id: 'adobe_stock',
          name: 'Adobe Stock',
          tagline: 'The original pipeline.',
          status: 'available',
          route: '/adobe-stock',
        ),
        PlatformEntry(
          id: 'freepik',
          name: 'Freepik',
          tagline: 'Vector-first marketplace.',
          status: 'coming_soon',
          route: '/freepik',
        ),
      ];

  @override
  Future<PlatformEntry> fetchPlatform(String platformId) async {
    final List<PlatformEntry> all = await fetchPlatforms();
    return all.firstWhere(
      (PlatformEntry entry) => entry.id == platformId,
      orElse: () => throw StateError('unknown platform $platformId'),
    );
  }
}

/// One-row gallery fake: the router tests care about routing, not paging —
/// every lens answers with the same tile so `/gallery` proves the tab swap.
class _FakeGalleryRepository implements GalleryRepository {
  @override
  Future<GalleryPage> fetchPage(GalleryQuery query) async => GalleryPage(
        items: <ImageRecord>[
          const ImageRecord(
            id: 'r1',
            filename: 'wire_loop.jpg',
            status: 'PASSED',
          ),
        ],
        total: 1,
      );

  @override
  Future<ImageRecord> fetchById(String recordId) async => const ImageRecord(
        id: 'r1',
        filename: 'wire_loop.jpg',
        status: 'PASSED',
      );

  @override
  Future<List<GalleryGroup>> fetchGroups() async => const <GalleryGroup>[];

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

/// One-batch process fake: the router tests care about routing, not the
/// pipeline — `/process` renders its empty state, `/process/:id` its header,
/// and the watch stream closes immediately (the events controller falls back
/// to polling, which the fake answers with the same canned detail).
class _FakeProcessRepository implements ProcessRepository {
  BatchDetail _detail() => BatchDetail(
        id: 'b-1',
        name: 'Raster run',
        mediaType: 'raster',
        steps: const <BatchStep>[BatchStep(key: 'ocr')],
        profileId: null,
        status: 'completed',
        stepProgress: null,
        error: null,
        recordCount: 0,
        createdAt: DateTime(2026, 10, 13),
        updatedAt: DateTime(2026, 10, 13),
        finishedAt: DateTime(2026, 10, 13),
        records: const <BatchRecord>[],
      );

  @override
  Future<BatchList> fetchBatches({int limit = 50}) async =>
      const BatchList(items: <Batch>[], total: 0);

  @override
  Future<BatchDetail> fetchBatchDetail(String batchId) async => _detail();

  @override
  Stream<BatchSnapshot> watchBatch(String batchId) =>
      const Stream<BatchSnapshot>.empty();

  @override
  Future<StepCatalog> fetchStepCatalog({String? mediaType}) async =>
      const StepCatalog(order: <String>['ocr'], steps: <StepDefinition>[]);

  @override
  Future<Batch> runBatch(String batchId) async => _detail();

  @override
  Future<Batch> cancelBatch(String batchId) async => _detail();

  @override
  Future<Batch> createBatch({
    required String name,
    required String mediaType,
    required List<BatchStep> steps,
    String? profileId,
  }) async =>
      _detail();

  @override
  Future<void> deleteBatch(String batchId) async {}

  @override
  Future<List<StepProfile>> fetchProfiles({String? mediaType}) async =>
      const <StepProfile>[];

  @override
  Future<StepProfile> createProfile({
    required String name,
    required String mediaType,
    required List<BatchStep> steps,
  }) async =>
      throw UnimplementedError();
}

/// Settings API fake so `/more/account` never leaves the test process; the
/// About row's health ping is stubbed through [activeHealthProvider].
class _FakeSettingsRepository implements SettingsRepository {
  @override
  Future<AppSettings> fetch() async => const AppSettings(
        llmBaseUrl: '',
        llmModel: '',
        llmApiKeyMasked: '',
        llmApiKeySet: false,
        llmContextWindow: 32768,
        braveSearchEnabled: false,
        braveSearchApiKeyMasked: '',
        braveSearchApiKeySet: false,
        effectiveBaseUrl: 'http://localhost:4006/api/gateway/v1',
        effectiveModel: 'OpenRouter-Free-Endpoint',
        effectiveUsesBrave: false,
      );

  @override
  Future<AppSettings> update(Map<String, dynamic> patch) => fetch();

  @override
  Future<SettingsTestResult> test([Map<String, dynamic>? candidate]) async =>
      const SettingsTestResult(ok: true, model: 'stub');

  @override
  Future<AppSettings> reset() => fetch();

  @override
  Future<String?> fetchUsername() async => 'admin';
}

/// Redirect matrix for the M1+M2 routes (05 §1.2), driven through real
/// [createRouter] instances so `refreshListenable` flips are covered too.
void main() {
  setUpAll(() {
    GoogleFonts.config.allowRuntimeFetching = false;
  });

  late ValueNotifier<AuthStatus> status;
  late GoRouter router;

  Future<void> pumpRouter(
    WidgetTester tester, {
    required AuthStatus initial,
    String location = '/splash',
  }) async {
    SharedPreferences.setMockInitialValues({});
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    status = ValueNotifier<AuthStatus>(initial);
    router = createRouter(
      currentStatus: () => status.value,
      refreshListenable: status,
      initialLocation: location,
    );
    // Splash probe hangs forever (cap far away) so the screen never decides;
    // its timer is cancelled on dispose at teardown.
    final SplashDependencies hanging = SplashDependencies(
      probe: () => Completer<void>().future,
      cap: const Duration(days: 1),
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          splashDependenciesProvider.overrideWithValue(hanging),
          sharedPreferencesProvider.overrideWithValue(prefs),
          platformRepositoryProvider
              .overrideWithValue(_FakePlatformRepository()),
          galleryRepositoryProvider.overrideWithValue(_FakeGalleryRepository()),
          processRepositoryProvider.overrideWithValue(_FakeProcessRepository()),
          settingsRepositoryProvider
              .overrideWithValue(_FakeSettingsRepository()),
          activeHealthProvider.overrideWith((Ref ref) async => true),
        ],
        child: MaterialApp.router(
          theme: buildAppTheme(),
          routerConfig: router,
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
  }

  tearDown(() {
    status.dispose();
  });

  testWidgets('unknown at /splash stays on the splash screen', (
    WidgetTester tester,
  ) async {
    await pumpRouter(tester, initial: AuthStatus.unknown);

    expect(find.byType(SplashScreen), findsOneWidget);
    expect(find.text('AI STOCK STUDIO'), findsOneWidget);

    await tester.pump(const Duration(milliseconds: 500));
    expect(find.byType(SplashScreen), findsOneWidget);
  });

  testWidgets('unauthenticated at /hub redirects to /login', (
    WidgetTester tester,
  ) async {
    await pumpRouter(
      tester,
      initial: AuthStatus.unauthenticated,
      location: '/hub',
    );

    expect(find.byType(LoginScreen), findsOneWidget);
    expect(find.byType(PlatformHubScreen), findsNothing);
    expect(find.text('Username'), findsOneWidget);
  });

  testWidgets('authenticated at /login redirects to /hub', (
    WidgetTester tester,
  ) async {
    await pumpRouter(
      tester,
      initial: AuthStatus.authenticated,
      location: '/login',
    );

    expect(find.byType(PlatformHubScreen), findsOneWidget);
    expect(find.text('AI STOCK STUDIO'), findsOneWidget);
  });

  testWidgets('authenticated at /hub stays on /hub', (
    WidgetTester tester,
  ) async {
    await pumpRouter(
      tester,
      initial: AuthStatus.authenticated,
      location: '/hub',
    );

    expect(find.byType(PlatformHubScreen), findsOneWidget);
    expect(find.byType(LoginScreen), findsNothing);
  });

  testWidgets('flipping the status via refreshListenable redirects', (
    WidgetTester tester,
  ) async {
    await pumpRouter(
      tester,
      initial: AuthStatus.unauthenticated,
      location: '/login',
    );
    expect(find.byType(LoginScreen), findsOneWidget);

    status.value = AuthStatus.authenticated;
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.byType(PlatformHubScreen), findsOneWidget);
  });

  testWidgets('authenticated at /gallery swaps the tab placeholder for the '
      'gallery screen (M3)', (WidgetTester tester) async {
    await pumpRouter(
      tester,
      initial: AuthStatus.authenticated,
      location: '/gallery',
    );

    expect(find.byType(GalleryScreen), findsOneWidget);
    expect(find.byType(GalleryDetailScreen), findsNothing);
    expect(find.byType(ShellBottomNav), findsOneWidget); // tab bar present

    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('wire_loop.jpg'), findsOneWidget);
  });

  testWidgets('authenticated at /gallery/:recordId opens detail inside the '
      'gallery branch (tabs stay visible — R4)', (WidgetTester tester) async {
    await pumpRouter(
      tester,
      initial: AuthStatus.authenticated,
      location: '/gallery/r1',
    );

    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump(const Duration(milliseconds: 1200)); // detail stamp-in
    await tester.pump();

    expect(find.byType(GalleryDetailScreen), findsOneWidget);
    // R4: the detail page rides the gallery branch — the tab bar (and the
    // queue indicator above it) stay visible while inspecting.
    expect(find.byType(ShellBottomNav), findsOneWidget);
    expect(find.byType(QueueIndicatorBar), findsOneWidget);
    // The grid stays on the branch stack below (its element is not built
    // while the opaque detail covers it — popping restores it, asserted by
    // the back-nav test above).
    expect(find.byType(GalleryScreen), findsNothing);
  });

  testWidgets('back from /gallery/:recordId pops to /gallery inside the '
      'branch (Android back)', (WidgetTester tester) async {
    await pumpRouter(
      tester,
      initial: AuthStatus.authenticated,
      location: '/gallery/r1',
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.byType(GalleryDetailScreen), findsOneWidget);
    expect(router.canPop(), isTrue); // Navigator.canPop semantics via router.

    router.pop();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.byType(GalleryDetailScreen), findsNothing);
    expect(find.byType(GalleryScreen), findsOneWidget);
    expect(find.byType(ShellBottomNav), findsOneWidget); // still in the tab
    expect(router.canPop(), isFalse); // branch back at its root
  });

  testWidgets('tab-hopping to Queue and back restores the open detail page '
      '(R4)', (WidgetTester tester) async {
    await pumpRouter(
      tester,
      initial: AuthStatus.authenticated,
      location: '/gallery/r1',
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    await tester.tap(find.text('QUEUE'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.byType(QueueScreen), findsOneWidget);
    expect(find.byType(GalleryDetailScreen), findsNothing);

    await tester.tap(find.text('GALLERY'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    // Where I left off: still on the record, not the grid root.
    expect(find.byType(GalleryDetailScreen), findsOneWidget);
    expect(find.byType(ShellBottomNav), findsOneWidget);
  });

  testWidgets('authenticated at /queue swaps the tab placeholder for the '
      'queue screen (R4)', (WidgetTester tester) async {
    await pumpRouter(
      tester,
      initial: AuthStatus.authenticated,
      location: '/queue',
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.byType(QueueScreen), findsOneWidget);
    expect(find.byType(TabPlaceholder), findsNothing); // placeholder retired
    expect(find.byType(ShellBottomNav), findsOneWidget); // tab bar present
    expect(find.text('Nothing queued'), findsOneWidget); // empty state
  });

  testWidgets('authenticated at /process opens the batch list outside the '
      'shell (removed from the tabs — R4)', (WidgetTester tester) async {
    await pumpRouter(
      tester,
      initial: AuthStatus.authenticated,
      location: '/process',
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.byType(ProcessScreen), findsOneWidget);
    expect(find.byType(TabPlaceholder), findsNothing); // placeholder retired
    // Root-level /process keeps "Back to batches" working, but the QUEUE
    // tab replaced PROCESS in the shell (tabs hidden here).
    expect(find.byType(ShellBottomNav), findsNothing);
    expect(find.text('No batches yet'), findsOneWidget); // fake empty state
  });

  testWidgets('authenticated at /process/new opens the wizard outside the '
      'shell (tabs hidden)', (WidgetTester tester) async {
    await pumpRouter(
      tester,
      initial: AuthStatus.authenticated,
      location: '/process/new',
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.byType(NewBatchScreen), findsOneWidget);
    expect(find.byType(ProcessScreen), findsNothing);
    expect(find.byType(ShellBottomNav), findsNothing);
    expect(find.text('What are we processing?'), findsOneWidget);
  });

  testWidgets('authenticated at /process/:batchId opens detail outside the '
      'shell (tabs hidden)', (WidgetTester tester) async {
    await pumpRouter(
      tester,
      initial: AuthStatus.authenticated,
      location: '/process/b-1',
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.byType(BatchDetailScreen), findsOneWidget);
    expect(find.byType(ProcessScreen), findsNothing);
    expect(find.byType(ShellBottomNav), findsNothing);
    expect(find.text('Raster run'), findsOneWidget);
  });

  testWidgets('authenticated at /delivery swaps the tab placeholder for the '
      'delivery screen (M4)', (WidgetTester tester) async {
    await pumpRouter(
      tester,
      initial: AuthStatus.authenticated,
      location: '/delivery',
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.byType(DeliveryScreen), findsOneWidget);
    expect(find.byType(TabPlaceholder), findsNothing);
    expect(find.byType(ShellBottomNav), findsOneWidget); // tab bar present
  });

  testWidgets('authenticated at /more swaps the placeholder for the M5 '
      'settings screen (tab bar kept)', (WidgetTester tester) async {
    await pumpRouter(
      tester,
      initial: AuthStatus.authenticated,
      location: '/more',
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.byType(SettingsScreen), findsOneWidget);
    expect(find.byType(TabPlaceholder), findsNothing);
    expect(find.byType(ShellBottomNav), findsOneWidget); // tab bar present
    expect(find.text('Connection profiles'), findsOneWidget);
  });

  testWidgets('authenticated at /more/connections opens the profile list '
      'outside the shell (tabs hidden)', (WidgetTester tester) async {
    await pumpRouter(
      tester,
      initial: AuthStatus.authenticated,
      location: '/more/connections',
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.byType(ConnectionsScreen), findsOneWidget);
    expect(find.byType(SettingsScreen), findsNothing);
    expect(find.byType(ShellBottomNav), findsNothing);
    expect(find.text('Tunnel'), findsOneWidget);
  });

  testWidgets('authenticated at /more/connections/:profileId opens the '
      'editor outside the shell (tabs hidden)', (WidgetTester tester) async {
    await pumpRouter(
      tester,
      initial: AuthStatus.authenticated,
      location: '/more/connections/tunnel',
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.byType(ConnectionEditorScreen), findsOneWidget);
    expect(find.byType(ShellBottomNav), findsNothing);
    expect(find.text('Activate'), findsOneWidget); // activation section
  });

  testWidgets('authenticated at /more/account opens the account screen '
      'outside the shell (tabs hidden)', (WidgetTester tester) async {
    await pumpRouter(
      tester,
      initial: AuthStatus.authenticated,
      location: '/more/account',
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.byType(AccountScreen), findsOneWidget);
    expect(find.byType(ShellBottomNav), findsNothing);
    expect(find.text('Local session · one seat'), findsOneWidget);
    expect(find.text('METADATA GATEWAY'), findsOneWidget); // LabelCaps
  });

  testWidgets('authenticated at /more/about opens the about screen outside '
      'the shell (tabs hidden)', (WidgetTester tester) async {
    await pumpRouter(
      tester,
      initial: AuthStatus.authenticated,
      location: '/more/about',
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.byType(AboutScreen), findsOneWidget);
    expect(find.byType(ShellBottomNav), findsNothing);
    expect(find.text('Version 1.0.0+1'), findsWidgets); // header
    expect(find.text('DIAGNOSTICS'), findsOneWidget); // LabelCaps

    // Licenses row sits below the fold on the default test surface.
    await tester.scrollUntilVisible(
      find.text('Open-source licenses'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pump();
    expect(find.text('Open-source licenses'), findsOneWidget);
  });

  testWidgets('authenticated at /error opens the full-screen error with the '
      'server reason and no tab bar', (WidgetTester tester) async {
    await pumpRouter(
      tester,
      initial: AuthStatus.authenticated,
      location: '/error?reason=server',
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.byType(ErrorScreen), findsOneWidget);
    expect(find.byType(ShellBottomNav), findsNothing); // tabs hidden
    expect(find.text('OUT OF ORDER'), findsOneWidget);
    expect(find.text('Server trouble.'), findsOneWidget);
    expect(find.text('Choose another profile'), findsOneWidget);
  });

  testWidgets('unauthenticated at /error still bounces to /login', (
    WidgetTester tester,
  ) async {
    await pumpRouter(
      tester,
      initial: AuthStatus.unauthenticated,
      location: '/error',
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.byType(LoginScreen), findsOneWidget);
    expect(find.byType(ErrorScreen), findsNothing);
  });
}
