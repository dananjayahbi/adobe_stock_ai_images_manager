import 'package:ai_stock_studio/app/theme/theme.dart';
import 'package:ai_stock_studio/features/settings/data/profile_store.dart';
import 'package:ai_stock_studio/features/settings/presentation/settings_controller.dart';
import 'package:ai_stock_studio/features/settings/presentation/settings_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Minimal probe router: `/more` (real SettingsScreen) over stub targets so
/// row taps assert navigation without pulling the whole route tree in.
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
  int clearCalls = 0;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    prefs = await SharedPreferences.getInstance();
    clearCalls = 0;
  });

  GoRouter buildRouter() => GoRouter(
        initialLocation: '/more',
        routes: <RouteBase>[
          GoRoute(
            path: '/more',
            builder: (context, state) => const SettingsScreen(),
          ),
          GoRoute(
            path: '/hub',
            builder: (context, state) => const _Stub('HUB STUB'),
          ),
          GoRoute(
            path: '/more/connections',
            builder: (context, state) => const _Stub('CONNECTIONS STUB'),
          ),
          GoRoute(
            path: '/more/account',
            builder: (context, state) => const _Stub('ACCOUNT STUB'),
          ),
          GoRoute(
            path: '/more/about',
            builder: (context, state) => const _Stub('ABOUT STUB'),
          ),
        ],
      );

  Future<({ProviderContainer container, GoRouter router})> pumpSettings(
    WidgetTester tester,
  ) async {
    final ProviderContainer container = ProviderContainer(
      overrides: <Override>[
        sharedPreferencesProvider.overrideWithValue(prefs),
        clearImageCacheProvider.overrideWithValue(() async {
          clearCalls++;
        }),
      ],
    );
    addTearDown(container.dispose);
    final GoRouter router = buildRouter();
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

  Future<void> flushToast(WidgetTester tester) async {
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump(const Duration(seconds: 3));
  }

  testWidgets('renders the four AppCard groups plus the platform row', (
    WidgetTester tester,
  ) async {
    final ({ProviderContainer container, GoRouter router}) flow =
        await pumpSettings(tester);

    // Section headers (LabelCaps renders uppercased).
    expect(find.text('CONNECTIONS'), findsOneWidget);
    expect(find.text('ACCOUNT'), findsOneWidget);
    expect(find.text('APP'), findsOneWidget);
    expect(find.text('ABOUT'), findsOneWidget);

    // Rows with the active-profile caption baked in.
    expect(find.text('Connection profiles'), findsOneWidget);
    expect(
      find.text('Tunnel · studio.hotelgo.lk'),
      findsOneWidget,
    );
    expect(find.text('Account & gateway'), findsOneWidget);
    expect(find.text('Local session · one seat'), findsOneWidget);
    expect(find.text('Reduced motion'), findsOneWidget);
    expect(find.text('Clear image cache'), findsOneWidget);

    // Banner rides above the groups (05 §3).
    expect(find.text('TUNNEL · studio.hotelgo.lk'), findsOneWidget);
    expect(flow.container.read(activeProfileProvider).id, 'tunnel');

    // The platform row sits below the fold on the default test surface.
    await tester.scrollUntilVisible(
      find.text('Switch platform'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pump();
    expect(find.text('Switch platform'), findsOneWidget);
  });

  testWidgets('reduced-motion switch flips forceReducedMotionProvider', (
    WidgetTester tester,
  ) async {
    final ({ProviderContainer container, GoRouter router}) flow =
        await pumpSettings(tester);
    expect(flow.container.read(forceReducedMotionProvider), isFalse);

    await tester.ensureVisible(find.byType(Switch));
    await tester.pump();
    await tester.tap(find.byType(Switch));
    await tester.pump();
    expect(flow.container.read(forceReducedMotionProvider), isTrue);

    await tester.tap(find.byType(Switch));
    await tester.pump();
    expect(flow.container.read(forceReducedMotionProvider), isFalse);
  });

  testWidgets('Clear image cache invokes the seam and toasts', (
    WidgetTester tester,
  ) async {
    await pumpSettings(tester);
    expect(clearCalls, 0);

    await tester.ensureVisible(find.text('Clear image cache'));
    await tester.pump();
    await tester.tap(find.text('Clear image cache'));
    await tester.pump();

    expect(clearCalls, 1);
    expect(find.text('Image cache cleared.'), findsOneWidget);

    await flushToast(tester);
    expect(find.byType(SettingsScreen), findsOneWidget); // never left /more
  });

  testWidgets('platform-switch row navigates to /hub via the router', (
    WidgetTester tester,
  ) async {
    await pumpSettings(tester);

    await tester.scrollUntilVisible(
      find.text('Switch platform'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pump();
    await tester.tap(find.text('Switch platform'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.text('HUB STUB'), findsOneWidget);
    expect(find.byType(SettingsScreen), findsNothing);
  });

  testWidgets('Connections row navigates to /more/connections', (
    WidgetTester tester,
  ) async {
    await pumpSettings(tester);

    await tester.ensureVisible(find.text('Connection profiles'));
    await tester.pump();
    await tester.tap(find.text('Connection profiles'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.text('CONNECTIONS STUB'), findsOneWidget);
    expect(find.byType(SettingsScreen), findsNothing);
  });
}
