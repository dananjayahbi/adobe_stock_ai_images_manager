import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';

import 'package:ai_stock_studio/app/theme/theme.dart';
import 'package:ai_stock_studio/features/gallery/domain/image_record.dart';
import 'package:ai_stock_studio/features/gallery/presentation/keyword_chips.dart';
import 'package:ai_stock_studio/features/gallery/presentation/metadata_sheet.dart';

/// Long enough to force multiple runs at any font metric, short phrases
/// only — none collide with the title/description fixture text.
const List<String> kKeywords = <String>[
  'wire loop',
  'sculpting',
  'ceramics',
  'pottery tool',
  'handmade craft',
  'studio gear',
  'clay shaping',
  'artisan workshop',
  'kiln firing',
  'glazing',
  'wheel throwing',
  'hand building',
];

ImageRecord buildRecord() {
  return ImageRecord(
    id: 'r1',
    filename: 'wire_loop.jpg',
    status: 'PASSED',
    state: 'APPROVED',
    thumbnailPath: null,
    generatedTitle: 'Wire loop sculpting tool',
    generatedDescription: 'A fine loop tool for shaping clay.',
    generatedKeywords: kKeywords,
    acceptanceScore: 0.91,
    width: 2048,
    height: 2048,
    fileSizeBytes: 255416,
  );
}

void main() {
  setUpAll(() {
    // Never hit fonts.google.com from tests (03 §5).
    TestWidgetsFlutterBinding.ensureInitialized();
    GoogleFonts.config.allowRuntimeFetching = false;
  });

  Future<void> pumpChips(WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: buildAppTheme(),
        home: const Scaffold(
          body: Padding(
            padding: EdgeInsets.all(16),
            child: KeywordChips(keywords: kKeywords),
          ),
        ),
      ),
    );
    await tester.pump();
  }

  testWidgets('renders every keyword once inside a single Wrap', (
    WidgetTester tester,
  ) async {
    await pumpChips(tester);

    // The wall is one Wrap of chips — not a Column / one-widget-per-line.
    final Finder wrap = find.descendant(
      of: find.byType(KeywordChips),
      matching: find.byType(Wrap),
    );
    expect(wrap, findsOneWidget);

    final Finder chips = find.descendant(
      of: wrap,
      matching: find.byType(KeywordChip),
    );
    expect(chips, findsNWidgets(kKeywords.length));

    for (final String keyword in kKeywords) {
      expect(find.text(keyword), findsOneWidget, reason: keyword);
    }
  });

  testWidgets('chips are content-sized and share runs (no full-width '
      'stacking)', (WidgetTester tester) async {
    await pumpChips(tester);

    final Finder wrap = find.descendant(
      of: find.byType(KeywordChips),
      matching: find.byType(Wrap),
    );
    final Finder chips = find.descendant(
      of: wrap,
      matching: find.byType(KeywordChip),
    );
    final double wrapWidth = tester.getSize(wrap).width;

    // Root-cause guard: an alignment-bearing chip expands to the wrap's
    // full width, forcing one chip per line — every chip must be narrower.
    final Set<double> rows = <double>{};
    for (int i = 0; i < kKeywords.length; i++) {
      final Finder chip = chips.at(i);
      expect(
        tester.getSize(chip).width,
        lessThan(wrapWidth),
        reason: '${kKeywords[i]} must hug its label, not fill the wrap',
      );
      rows.add(tester.getTopLeft(chip).dy);
    }

    // Dense flow: fewer runs than chips means at least two chips share a
    // line (the stacked bug produced exactly one run per keyword).
    expect(
      rows.length,
      lessThan(kKeywords.length),
      reason: 'keywords should flow side by side, not one per row',
    );

    // Small label per spec (11–12 px band).
    final Text label = tester.widget<Text>(find.text(kKeywords.first));
    expect(label.style?.fontSize, 11);
  });

  testWidgets('metadata sheet shows every keyword through the chip wall', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: buildAppTheme(),
        home: Scaffold(
          body: MetadataSheet(record: buildRecord(), loading: false),
        ),
      ),
    );
    await tester.pump();

    final Finder sheet = find.byType(MetadataSheet);
    expect(
      find.descendant(of: sheet, matching: find.byType(KeywordChips)),
      findsOneWidget,
    );
    for (final String keyword in kKeywords) {
      expect(
        find.descendant(of: sheet, matching: find.text(keyword)),
        findsOneWidget,
        reason: keyword,
      );
    }

    // Sheet chips are content-sized too (wrap width < card width).
    final Finder sheetChips = find.descendant(
      of: sheet,
      matching: find.byType(KeywordChip),
    );
    expect(sheetChips, findsNWidgets(kKeywords.length));
    final Finder sheetWrap = find.descendant(
      of: find.byType(KeywordChips),
      matching: find.byType(Wrap),
    );
    final double sheetWrapWidth = tester.getSize(sheetWrap).width;
    for (int i = 0; i < kKeywords.length; i++) {
      expect(
        tester.getSize(sheetChips.at(i)).width,
        lessThan(sheetWrapWidth),
        reason: kKeywords[i],
      );
    }
  });
}
