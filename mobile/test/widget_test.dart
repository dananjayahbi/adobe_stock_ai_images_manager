import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:ai_stock_studio/app/app.dart';
import 'package:ai_stock_studio/app/splash_screen.dart';
import 'package:ai_stock_studio/features/settings/data/profile_store.dart';

void main() {
  setUpAll(() {
    GoogleFonts.config.allowRuntimeFetching = false;
  });

  testWidgets('boots into the splash wordmark without hanging', (
    WidgetTester tester,
  ) async {
    SharedPreferences.setMockInitialValues({});
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    // The default probe would hit the network — park it; its 1-day cap timer
    // is cancelled by SplashScreen.dispose during teardown.
    final Completer<void> parked = Completer<void>();

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          sharedPreferencesProvider.overrideWithValue(prefs),
          splashDependenciesProvider.overrideWithValue(
            SplashDependencies(
              probe: () => parked.future,
              cap: const Duration(days: 1),
            ),
          ),
        ],
        child: const App(),
      ),
    );
    await tester.pump();

    expect(find.text('AI STOCK STUDIO'), findsOneWidget);
    expect(find.byType(SplashScreen), findsOneWidget);

    await tester.pump(const Duration(milliseconds: 100));
    expect(find.byType(SplashScreen), findsOneWidget);
  });
}
