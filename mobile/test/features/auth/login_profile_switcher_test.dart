import 'package:ai_stock_studio/app/theme/theme.dart';
import 'package:ai_stock_studio/features/auth/presentation/login_screen.dart';
import 'package:ai_stock_studio/features/settings/data/health_api.dart';
import 'package:ai_stock_studio/features/settings/data/profile_store.dart';
import 'package:ai_stock_studio/features/settings/presentation/settings_controller.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show ProviderOrFamily;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:lucide_flutter/lucide_flutter.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUpAll(() {
    GoogleFonts.config.allowRuntimeFetching = false;
    // In-memory Keystore for the switch flow's jar reads.
    FlutterSecureStorage.setMockInitialValues(<String, String>{});
  });

  late SharedPreferences prefs;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    prefs = await SharedPreferences.getInstance();
  });

  /// Adds the dev loopback profile beside the tunnel-only seed so the
  /// picker has a second candidate to switch to.
  Future<void> seedLocal() async {
    await ProfileStore(prefs).upsert(ProfileStore.localSeed);
  }

  Future<void> pumpLogin(
    WidgetTester tester, {
    Future<HealthProbeResult> Function(String baseUrl)? probe,
  }) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          sharedPreferencesProvider.overrideWithValue(prefs),
          if (probe != null)
            profileHealthProbeProvider.overrideWithValue(probe),
          // Nothing is cached pre-login — keep invalidation hermetic.
          profileSwitchTargetsProvider
              .overrideWithValue(const <ProviderOrFamily>[]),
        ],
        child: MaterialApp(
          theme: buildAppTheme(),
          home: const Scaffold(body: LoginScreen()),
        ),
      ),
    );
    await tester.pump(const Duration(milliseconds: 400));
  }

  testWidgets('row shows the tunnel profile before auth', (tester) async {
    await pumpLogin(tester);

    expect(find.text('CONNECTION'), findsOneWidget);
    expect(find.text('Tunnel'), findsOneWidget);
    expect(find.text('studio.hotelgo.lk'), findsOneWidget);
  });

  testWidgets('tapping the row opens the health-gated profile picker',
      (tester) async {
    await seedLocal();
    await pumpLogin(
      tester,
      probe: (String _) async => const HealthProbeResult.success(5),
    );

    await tester.tap(find.text('Tunnel'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.text('SWITCH CONNECTION'), findsOneWidget);
    expect(find.text('Local network'), findsOneWidget);
    expect(find.text('http://localhost:8007'), findsOneWidget);
    // Exactly one checkmark: the already-active tunnel row.
    expect(find.byIcon(LucideIcons.circleCheck), findsOneWidget);
  });

  testWidgets('reachable candidate activates and the row follows it',
      (tester) async {
    await seedLocal();
    await pumpLogin(
      tester,
      probe: (String url) async => url.contains('localhost')
          ? const HealthProbeResult.success(42)
          : const HealthProbeResult.failure('Host unreachable.'),
    );

    await tester.tap(find.text('Tunnel'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    await tester.tap(find.text('Local network'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump(const Duration(milliseconds: 400));

    // Sheet closed, row repointed, success toast surfaced.
    expect(find.text('SWITCH CONNECTION'), findsNothing);
    expect(find.text('localhost:8007'), findsOneWidget);
    expect(find.textContaining('Switched · 42 ms'), findsOneWidget);

    // Flush the toast timer so the test ends without a pending Timer.
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump(const Duration(seconds: 3));
    expect(find.textContaining('Switched · 42 ms'), findsNothing);
  });

  testWidgets('dead candidate keeps the current profile with inline error',
      (tester) async {
    await seedLocal();
    await pumpLogin(
      tester,
      probe: (String _) async =>
          const HealthProbeResult.failure('Host unreachable.'),
    );

    await tester.tap(find.text('Tunnel'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    await tester.tap(find.text('Local network'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));

    // Sheet stays open with the reason inline; nothing switched.
    expect(find.text('SWITCH CONNECTION'), findsOneWidget);
    expect(find.text('Host unreachable.'), findsOneWidget);

    // Dismiss via the barrier; the row is unchanged behind it.
    await tester.tapAt(const Offset(8, 8));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('SWITCH CONNECTION'), findsNothing);
    expect(find.text('Tunnel'), findsOneWidget);
    expect(find.text('studio.hotelgo.lk'), findsOneWidget);
  });

  testWidgets('edit-address verifies and persists a raw IP (no DNS needed)',
      (tester) async {
    await pumpLogin(
      tester,
      probe: (String _) async => const HealthProbeResult.success(42),
    );

    await tester.tap(find.text('Tunnel'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    await tester.tap(find.text('Edit connection address…'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));

    expect(find.text('EDIT ADDRESS'), findsOneWidget);
    expect(find.text('https://studio.hotelgo.lk'), findsOneWidget);

    await tester.enterText(
      find.widgetWithText(TextField, 'https://studio.hotelgo.lk'),
      'http://192.168.1.10:8007',
    );
    await tester.tap(find.text('Save & test'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump(const Duration(milliseconds: 400));

    // Sheet closed, row repointed, verification toast surfaced.
    expect(find.text('EDIT ADDRESS'), findsNothing);
    expect(find.text('192.168.1.10:8007'), findsOneWidget);
    expect(find.textContaining('Address verified · 42 ms'), findsOneWidget);

    // Flush the toast timer so the test ends without a pending Timer.
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump(const Duration(seconds: 3));
    expect(find.textContaining('Address verified · 42 ms'), findsNothing);
  });
}