import 'package:ai_stock_studio/app/theme/theme.dart';
import 'package:ai_stock_studio/app/theme/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';

void main() {
  setUpAll(() {
    // Keep tests hermetic: never fetch fonts over HTTP in the test zone
    // (styles still resolve to their family names; rendering falls back).
    GoogleFonts.config.allowRuntimeFetching = false;
  });

  test('buildAppTheme maps the vintage brand roles (dark-only)', () {
    final ThemeData theme = buildAppTheme();

    expect(theme.brightness, Brightness.dark);
    expect(theme.useMaterial3, isTrue);
    // §1.1: page chrome is leather #1a130c.
    expect(theme.scaffoldBackgroundColor, AppColors.leather);
    // §1.1 role spot-checks.
    expect(theme.colorScheme.primary, AppColors.oxblood500);
    expect(theme.colorScheme.secondary, AppColors.brass400);
    expect(theme.colorScheme.onSurface, AppColors.ink800);
    // Material's blue elevation tint must never surface.
    expect(theme.colorScheme.surfaceTint, Colors.transparent);
    expect(theme.appBarTheme.backgroundColor, AppColors.leather);
    expect(theme.navigationBarTheme.indicatorColor, AppColors.brass400);
    // AppColors token spot-check (oxblood-500 from tailwind.config.ts).
    expect(AppColors.oxblood500, const Color(0xFF8b3a2f));
  });

  testWidgets('bodyLarge renders with the EB Garamond family',
      (WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: buildAppTheme(),
        home: Scaffold(
          body: Builder(
            builder: (BuildContext context) {
              return Text(
                'x',
                style: Theme.of(context).textTheme.bodyLarge,
              );
            },
          ),
        ),
      ),
    );

    final TextStyle? style = tester.widget<Text>(find.text('x')).style;
    expect(style, isNotNull);
    expect(style!.fontFamily, isNotNull);
    // google_fonts names the family 'EBGaramond' (no space) with an
    // 'EBGaramond' fallback — accept either spelling.
    final String family = style.fontFamily!.toLowerCase();
    expect(
      family.contains('ebgaramond') || family.contains('eb garamond'),
      isTrue,
      reason: 'bodyLarge family was "${style.fontFamily}"',
    );
    expect(style.fontSize, 16);
  });
}
