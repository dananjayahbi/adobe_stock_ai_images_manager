import 'package:ai_stock_studio/app/error_screen.dart';
import 'package:ai_stock_studio/app/theme/theme.dart';
import 'package:ai_stock_studio/core/widgets/primary_button.dart';
import 'package:ai_stock_studio/features/settings/data/health_api.dart';
import 'package:ai_stock_studio/features/settings/data/profile_store.dart';
import 'package:ai_stock_studio/features/settings/presentation/settings_controller.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Scriptable `/health` outcome per call: succeeds from [succeedAt] (1-based)
/// onward, fails with the backoff reason before that (`-1` never succeeds).
class _ScriptedProbe {
  _ScriptedProbe({this.succeedAt = -1});

  final int succeedAt;
  int calls = 0;

  Future<HealthProbeResult> call(String baseUrl) async {
    calls++;
    if (calls == succeedAt) {
      return const HealthProbeResult.success(12);
    }
    return const HealthProbeResult.failure('Timed out after 3 s.');
  }
}

class _Stub extends StatelessWidget {
  const _Stub(this.text);

  final String text;

  @override
  Widget build(BuildContext context) =>
      Scaffold(body: Center(child: Text(text)));
}

void main() {
  setUpAll(() {
    GoogleFonts.config.allowRuntimeFetching = false;
    TestWidgetsFlutterBinding.ensureInitialized();
    TestWidgetsFlutterBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, (call) async => null);
  });

  late SharedPreferences prefs;
  late _ScriptedProbe probe;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    prefs = await SharedPreferences.getInstance();
    probe = _ScriptedProbe();
  });

  GoRouter buildRouter({String location = '/error'}) => GoRouter(
        initialLocation: location,
        routes: <RouteBase>[
          GoRoute(
            path: '/error',
            builder: (context, state) => ErrorScreen(
              reason: state.uri.queryParameters['reason'] ?? 'offline',
            ),
          ),
          GoRoute(
            path: '/hub',
            builder: (context, state) => const _Stub('HUB STUB'),
          ),
          GoRoute(
            path: '/more/connections',
            builder: (context, state) =>
                const _Stub('CONNECTIONS STUB'),
          ),
        ],
      );

  Future<({ProviderContainer container, GoRouter router})> pumpError(
    WidgetTester tester, {
    String location = '/error',
  }) async {
    final ProviderContainer container = ProviderContainer(
      overrides: <Override>[
        sharedPreferencesProvider.overrideWithValue(prefs),
        profileHealthProbeProvider.overrideWithValue(probe.call),
      ],
    );
    addTearDown(container.dispose);
    final GoRouter router = buildRouter(location: location);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp.router(
          theme: buildAppTheme(),
          routerConfig: router,
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    return (container: container, router: router);
  }

  testWidgets(
      'retry loop fires with 2/5/10 s backoff — three attempts observed, '
      'then stops after exhausting the schedule', (WidgetTester tester) async {
    await pumpError(tester);

    // Offline flavor (05 §2.11): stamp + headline + both actions.
    expect(find.text('NO SIGNAL'), findsOneWidget);
    expect(find.text('No signal.'), findsOneWidget);
    expect(find.text('Retry connection'), findsOneWidget);
    expect(find.text('Choose another profile'), findsOneWidget);
    expect(probe.calls, 0);

    // Attempt 1 fires immediately on tap.
    await tester.tap(find.text('Retry connection'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(probe.calls, 1);
    expect(find.text('ATTEMPT 1'), findsOneWidget);

    // Backoff 2 s → attempt 2 (third attempt checkpoint: 2 + 5 s).
    await tester.pump(const Duration(seconds: 2));
    await tester.pump(const Duration(milliseconds: 50));
    expect(probe.calls, 2);
    expect(find.text('ATTEMPT 2'), findsOneWidget);

    await tester.pump(const Duration(seconds: 5));
    await tester.pump(const Duration(milliseconds: 50));
    expect(probe.calls, 3);
    expect(find.text('ATTEMPT 3'), findsOneWidget);

    // Final 10 s backoff → attempt 4 fails and the loop stops.
    await tester.pump(const Duration(seconds: 10));
    await tester.pump(const Duration(milliseconds: 50));
    expect(probe.calls, 4);
    expect(find.text('ATTEMPT 4'), findsOneWidget);

    // Still stopped: no fifth attempt, Retry re-armed for a manual round.
    await tester.pump(const Duration(seconds: 30));
    await tester.pump(const Duration(milliseconds: 50));
    expect(probe.calls, 4);
    final PrimaryButton retry =
        tester.widget<PrimaryButton>(find.widgetWithText(
      PrimaryButton,
      'Retry connection',
    ));
    expect(retry.loading, isFalse);
    expect(find.byType(ErrorScreen), findsOneWidget); // never left /error
  });

  testWidgets('a successful probe mid-loop replaces the screen with /hub', (
    WidgetTester tester,
  ) async {
    probe = _ScriptedProbe(succeedAt: 3);
    await pumpError(tester);

    await tester.tap(find.text('Retry connection'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(probe.calls, 1);

    await tester.pump(const Duration(seconds: 2));
    await tester.pump(const Duration(milliseconds: 50));
    expect(probe.calls, 2);

    await tester.pump(const Duration(seconds: 5));
    await tester.pump(const Duration(milliseconds: 50));
    expect(probe.calls, 3);

    // Success → context.go('/hub'); no further probes.
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('HUB STUB'), findsOneWidget);
    expect(find.byType(ErrorScreen), findsNothing);
    expect(probe.calls, 3);
  });

  testWidgets("'Choose another profile' navigates to /more/connections", (
    WidgetTester tester,
  ) async {
    await pumpError(tester);

    await tester.tap(find.text('Choose another profile'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.text('CONNECTIONS STUB'), findsOneWidget);
    expect(find.byType(ErrorScreen), findsNothing);
    expect(probe.calls, 0); // navigation never starts the retry loop
  });

  testWidgets('server flavor renders the OUT OF ORDER variant', (
    WidgetTester tester,
  ) async {
    await pumpError(tester, location: '/error?reason=server');

    expect(find.text('OUT OF ORDER'), findsOneWidget);
    expect(find.text('Server trouble.'), findsOneWidget);
    expect(find.text('NO SIGNAL'), findsNothing);
  });
}
