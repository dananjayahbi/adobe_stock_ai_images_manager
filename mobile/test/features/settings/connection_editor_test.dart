import 'dart:async';

import 'package:ai_stock_studio/features/settings/data/health_api.dart';
import 'package:ai_stock_studio/features/settings/data/profile_store.dart';
import 'package:ai_stock_studio/features/settings/domain/connection_profile.dart';
import 'package:ai_stock_studio/features/settings/presentation/connection_editor_screen.dart';
import 'package:ai_stock_studio/features/settings/presentation/connections_screen.dart';
import 'package:ai_stock_studio/features/settings/presentation/settings_controller.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:ai_stock_studio/core/widgets/primary_button.dart';
import 'package:ai_stock_studio/core/widgets/secondary_button.dart';

/// HealthApi that never touches Dio — the banner's debounced probe fires
/// after profile switches, and tests must stay hermetic.
class _FakeHealthApi extends HealthApi {
  _FakeHealthApi() : super(Dio());

  @override
  Future<bool> ping() async => true;
}

void main() {
  setUpAll(() {
    GoogleFonts.config.allowRuntimeFetching = false;
    TestWidgetsFlutterBinding.ensureInitialized();
    // In-memory Keychain/Keystore: the switch flow reads the profile-scoped
    // session pair through the platform channel — never hit the real store.
    FlutterSecureStorage.setMockInitialValues(<String, String>{});
    // Haptics used by shell navigation land on this channel in tests.
    TestWidgetsFlutterBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, (call) async => null);
  });

  late SharedPreferences prefs;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    prefs = await SharedPreferences.getInstance();
    // Two-profile fixture (tunnel-only seed + local, local active) — the
    // editor/switch/delete flows all key off a second, active local profile.
    final ProfileStore fixture = ProfileStore(prefs);
    await fixture.upsert(ProfileStore.localSeed);
    await fixture.setActive('local');
  });

  ProfileStore store() => ProfileStore(prefs);

  GoRouter buildRouter() => GoRouter(
        initialLocation: '/more/connections',
        routes: <RouteBase>[
          GoRoute(
            path: '/more/connections',
            builder: (context, state) => const ConnectionsScreen(),
          ),
          GoRoute(
            path: '/more/connections/:profileId',
            builder: (context, state) => ConnectionEditorScreen(
              profileId: state.pathParameters['profileId'] ?? '',
            ),
          ),
        ],
      );

  Future<void> pumpFlow(
    WidgetTester tester,
    GoRouter router, {
    String? openProfileId,
  }) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          sharedPreferencesProvider.overrideWithValue(prefs),
          healthApiProvider.overrideWithValue(_FakeHealthApi()),
        ],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pump();
    if (openProfileId != null) {
      unawaited(router.push('/more/connections/$openProfileId'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
    }
  }

  Future<void> flushToast(WidgetTester tester) async {
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump(const Duration(seconds: 3));
  }

  Future<void> setBaseUrl(WidgetTester tester, String value) async {
    await tester.enterText(find.byType(TextFormField).at(1), value);
    await tester.pump();
  }

  testWidgets('invalid URL shows the inline error and blocks Save', (
    WidgetTester tester,
  ) async {
    final GoRouter router = buildRouter();
    await pumpFlow(tester, router, openProfileId: 'local');

    await setBaseUrl(tester, 'just-a-hostname');
    await tester.tap(find.widgetWithText(PrimaryButton, 'Save'));
    await tester.pump();

    expect(
      find.text('Enter a full http:// or https:// URL.'),
      findsOneWidget,
    );
    // Nothing persisted: the seeded local profile is untouched.
    expect(store().profiles(), hasLength(2));
    final ConnectionProfile local = store()
        .profiles()
        .firstWhere((ConnectionProfile p) => p.id == 'local');
    expect(local.baseUrl, 'http://localhost:8007');
    expect(local.label, 'Local network');
  });

  testWidgets('valid Save upserts the edited profile', (
    WidgetTester tester,
  ) async {
    final GoRouter router = buildRouter();
    await pumpFlow(tester, router, openProfileId: 'local');

    await tester.enterText(find.byType(TextFormField).first, 'Phone hotspot');
    await setBaseUrl(tester, 'http://192.168.43.1:8007');
    await tester.tap(find.widgetWithText(PrimaryButton, 'Save'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.text('Profile saved.'), findsOneWidget);

    final List<ConnectionProfile> profiles = store().profiles();
    expect(profiles, hasLength(2)); // upsert, never append-duplicate
    final ConnectionProfile edited = profiles
        .firstWhere((ConnectionProfile p) => p.id == 'local');
    expect(edited.label, 'Phone hotspot');
    expect(edited.baseUrl, 'http://192.168.43.1:8007');

    await flushToast(tester);
  });

  testWidgets('Test button reports success latency inline', (
    WidgetTester tester,
  ) async {
    final GoRouter router = buildRouter();
    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          sharedPreferencesProvider.overrideWithValue(prefs),
          healthApiProvider.overrideWithValue(_FakeHealthApi()),
          profileHealthProbeProvider
              .overrideWithValue((String baseUrl) async {
            return const HealthProbeResult.success(42);
          }),
        ],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pump();
    unawaited(router.push('/more/connections/local'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    await tester.tap(find.widgetWithText(SecondaryButton, 'Test'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.text('OK · 42 ms'), findsOneWidget);
  });

  testWidgets('health failure keeps the previous profile active', (
    WidgetTester tester,
  ) async {
    final GoRouter router = buildRouter();
    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          sharedPreferencesProvider.overrideWithValue(prefs),
          healthApiProvider.overrideWithValue(_FakeHealthApi()),
          profileHealthProbeProvider
              .overrideWithValue((String baseUrl) async {
            return const HealthProbeResult.failure('Host unreachable.');
          }),
        ],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pump();
    unawaited(router.push('/more/connections/tunnel'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    await tester.tap(find.widgetWithText(PrimaryButton, 'Activate'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(
      find.text('Could not switch — Host unreachable. '
          'The previous profile stays active.'),
      findsOneWidget,
    );
    // Persistence never flipped: still the pre-seeded active local profile.
    expect(prefs.getString(ProfileStore.activeKey), 'local');
    expect(store().activeProfile().id, 'local');
  });

  testWidgets('health success activates, toasts the latency and pops', (
    WidgetTester tester,
  ) async {
    final GoRouter router = buildRouter();
    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          sharedPreferencesProvider.overrideWithValue(prefs),
          healthApiProvider.overrideWithValue(_FakeHealthApi()),
          profileHealthProbeProvider
              .overrideWithValue((String baseUrl) async {
            return const HealthProbeResult.success(42);
          }),
        ],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pump();
    unawaited(router.push('/more/connections/tunnel'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    await tester.tap(find.widgetWithText(PrimaryButton, 'Activate'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump(const Duration(milliseconds: 300));

    // The switch landed in persistence…
    expect(prefs.getString(ProfileStore.activeKey), 'tunnel');
    // …the latency toast announced it…
    expect(find.text('Switched · 42 ms'), findsOneWidget);

    // Popped back to the list, which re-reads the store and shows the new
    // active card stamp.
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.byType(ConnectionsScreen), findsOneWidget);
    expect(find.byType(ConnectionEditorScreen), findsNothing);

    // Banner debounce (300 ms) fires the fake ping; then flush the toast.
    await flushToast(tester);
  });

  testWidgets('swipe-delete on the active profile is blocked', (
    WidgetTester tester,
  ) async {
    final GoRouter router = buildRouter();
    await pumpFlow(tester, router);

    expect(find.byType(ConnectionsScreen), findsOneWidget);
    await tester.drag(
      find.byKey(const ValueKey<String>('profile-local')),
      const Offset(-500, 0),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    expect(
      find.textContaining('active profile'),
      findsOneWidget,
    );
    // Still listed, still stored — neither UI nor store lost anything.
    expect(find.byKey(const ValueKey<String>('profile-local')),
        findsOneWidget);
    expect(store().profiles(), hasLength(2));

    await flushToast(tester);
  });

  testWidgets('swipe-delete on a passive profile confirms and removes it', (
    WidgetTester tester,
  ) async {
    final GoRouter router = buildRouter();
    await pumpFlow(tester, router);

    await tester.drag(
      find.byKey(const ValueKey<String>('profile-tunnel')),
      const Offset(-500, 0),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    // ConfirmDialog gates the destructive action (05 §2.9.1).
    expect(find.text('Delete profile?'), findsOneWidget);
    await tester.tap(find.widgetWithText(TextButton, 'Delete'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pump(const Duration(milliseconds: 400));

    expect(find.text('Profile removed.'), findsOneWidget);
    expect(store().profiles().map((ConnectionProfile p) => p.id),
        <String>['local']);
    expect(store().activeProfile().id, 'local'); // active untouched

    await flushToast(tester);
  });
}
