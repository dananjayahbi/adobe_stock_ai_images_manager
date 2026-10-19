import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:ai_stock_studio/app/theme/theme.dart';
import 'package:ai_stock_studio/features/platforms/data/platform_repository_impl.dart';
import 'package:ai_stock_studio/features/platforms/domain/platform.dart';
import 'package:ai_stock_studio/features/platforms/domain/platform_repository.dart';
import 'package:ai_stock_studio/features/platforms/presentation/platform_card.dart';
import 'package:ai_stock_studio/features/platforms/presentation/platform_hub_screen.dart';
import 'package:ai_stock_studio/features/settings/data/profile_store.dart';

/// Deterministic in-memory catalogue for pixel-stable goldens.
class _FakePlatformRepository implements PlatformRepository {
  const _FakePlatformRepository();

  static const List<PlatformEntry> _entries = <PlatformEntry>[
    PlatformEntry(
      id: 'adobe_stock',
      name: 'Adobe Stock',
      tagline: 'The original pipeline — audit, refine, and deliver AI images.',
      status: 'available',
      route: '/adobe-stock',
    ),
    PlatformEntry(
      id: 'freepik',
      name: 'Freepik',
      tagline:
          'Vector-first marketplace — illustrations, PSDs, and photos, coming soon.',
      status: 'coming_soon',
      route: '/freepik',
    ),
    PlatformEntry(
      id: 'vecteezy',
      name: 'Vecteezy',
      tagline: 'Creator-friendly vectors and photos — a fresh lane, coming soon.',
      status: 'coming_soon',
      route: '/vecteezy',
    ),
    PlatformEntry(
      id: 'dreamstime',
      name: 'Dreamstime',
      tagline: 'Community-driven stock with deep archives — coming soon.',
      status: 'coming_soon',
      route: '/dreamstime',
    ),
    PlatformEntry(
      id: '123rf',
      name: '123RF',
      tagline: 'Budget-minded marketplace with global reach — coming soon.',
      status: 'coming_soon',
      route: '/123rf',
    ),
    PlatformEntry(
      id: 'wirestock',
      name: 'Wirestock',
      tagline: 'One upload, many marketplaces — the aggregator route, coming soon.',
      status: 'coming_soon',
      route: '/wirestock',
    ),
  ];

  @override
  Future<List<PlatformEntry>> fetchPlatforms() async => _entries;

  @override
  Future<PlatformEntry> fetchPlatform(String platformId) async {
    return _entries.firstWhere(
      (PlatformEntry entry) => entry.id == platformId,
    );
  }
}

void main() {
  setUpAll(() {
    // Never hit fonts.google.com from tests (03 §5) — bundled/fallback only.
    GoogleFonts.config.allowRuntimeFetching = false;
  });

  Future<void> pumpHub(WidgetTester tester, {Size size = const Size(390, 844)}) async {
    SharedPreferences.setMockInitialValues({});
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    tester.view.physicalSize = size;
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          sharedPreferencesProvider.overrideWithValue(prefs),
          platformRepositoryProvider
              .overrideWithValue(const _FakePlatformRepository()),
        ],
        child: MaterialApp(
          theme: buildAppTheme(),
          home: const RepaintBoundary(
            key: ValueKey<String>('platform-hub'),
            child: PlatformHubScreen(),
          ),
        ),
      ),
    );
    // Let the async catalogue land, then let all stamp-in entrances finish
    // (6 cards × 60 ms stagger + 350 ms stamp ≈ 700 ms; pump past it).
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump(const Duration(milliseconds: 800));
  }

  testWidgets('golden: platform hub renders hero + card grid (phone, 1 col)', (
    WidgetTester tester,
  ) async {
    await pumpHub(tester);

    expect(find.byKey(const ValueKey<String>('platform-hub')), findsOneWidget);
    expect(find.text('AI STOCK STUDIO'), findsOneWidget);
    expect(find.text('Adobe Stock'), findsOneWidget);
    expect(find.text('OPEN'), findsOneWidget);
    expect(find.text('COMING SOON'), findsNWidgets(5));
    expect(find.byType(PlatformCard), findsNWidgets(6));

    // 390 dp wide → below the 600 dp breakpoint → 1 column: every card
    // spans the full content width, so cards stack vertically.
    final RenderBox firstCard = tester.renderObject<RenderBox>(
      find.byType(PlatformCard).first,
    );
    expect(firstCard.size.width, greaterThan(300));

    await expectLater(
      find.byKey(const ValueKey<String>('platform-hub')),
      matchesGoldenFile('platform_hub.png'),
    );
  });

  testWidgets('golden: platform hub switches to 2 columns ≥600 dp', (
    WidgetTester tester,
  ) async {
    await pumpHub(tester, size: const Size(800, 900));

    final RenderBox firstCard = tester.renderObject<RenderBox>(
      find.byType(PlatformCard).first,
    );
    final RenderBox secondCard = tester.renderObject<RenderBox>(
      find.byType(PlatformCard).at(1),
    );
    // Side-by-side: same row → equal widths well under the full span.
    expect(firstCard.size.width, greaterThan(300));
    expect(firstCard.size.width, lessThan(760));
    expect(
      secondCard.localToGlobal(Offset.zero).dy,
      firstCard.localToGlobal(Offset.zero).dy,
    );

    await expectLater(
      find.byKey(const ValueKey<String>('platform-hub')),
      matchesGoldenFile('platform_hub_wide.png'),
    );
  });
}
