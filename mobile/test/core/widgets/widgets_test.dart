import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:lucide_flutter/lucide_flutter.dart';

import 'package:ai_stock_studio/app/theme/tokens.dart';
import 'package:ai_stock_studio/core/widgets/app_card.dart';
import 'package:ai_stock_studio/core/widgets/async_view.dart';
import 'package:ai_stock_studio/core/widgets/dashed_divider.dart';
import 'package:ai_stock_studio/core/widgets/empty_state.dart';
import 'package:ai_stock_studio/core/widgets/error_view.dart';
import 'package:ai_stock_studio/core/widgets/ghost_button.dart';
import 'package:ai_stock_studio/core/widgets/label_caps.dart';
import 'package:ai_stock_studio/core/widgets/primary_button.dart';
import 'package:ai_stock_studio/core/widgets/secondary_button.dart';
import 'package:ai_stock_studio/core/widgets/skeleton_loader.dart';
import 'package:ai_stock_studio/core/widgets/stamp_badge.dart';
import 'package:ai_stock_studio/core/widgets/stamp_in.dart';
import 'package:ai_stock_studio/core/widgets/status_chip.dart';
import 'package:ai_stock_studio/core/widgets/thumbnail.dart';
import 'package:ai_stock_studio/core/widgets/toast_exception.dart';

Future<void> pumpApp(WidgetTester tester, Widget child) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: ThemeData.dark(useMaterial3: true),
      home: Scaffold(body: Center(child: child)),
    ),
  );
}

Iterable<double> opacityAncestors(WidgetTester tester, Finder text) {
  return tester
      .widgetList<Opacity>(
        find.ancestor(of: text, matching: find.byType(Opacity)),
      )
      .map((Opacity widget) => widget.opacity);
}

void main() {
  setUpAll(() {
    // Special Elite is not bundled in tests; fail fast instead of fetching.
    GoogleFonts.config.allowRuntimeFetching = false;
  });

  testWidgets('PrimaryButton renders label, meets 48dp and fires onPressed', (
    WidgetTester tester,
  ) async {
    bool tapped = false;
    await pumpApp(
      tester,
      PrimaryButton(
        label: 'Save batch',
        onPressed: () => tapped = true,
      ),
    );

    expect(find.text('Save batch'), findsOneWidget);
    expect(
      tester.getSize(find.byType(PrimaryButton)).height,
      greaterThanOrEqualTo(48),
    );

    await tester.tap(find.text('Save batch'));
    await tester.pump();
    expect(tapped, isTrue);
  });

  testWidgets('PrimaryButton loading swaps label for spinner and blocks taps', (
    WidgetTester tester,
  ) async {
    int taps = 0;
    await pumpApp(
      tester,
      PrimaryButton(
        label: 'Uploading',
        onPressed: () => taps++,
        loading: true,
      ),
    );

    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    // Label keeps its layout slot but is visually hidden.
    expect(opacityAncestors(tester, find.text('Uploading')), contains(0.0));

    await tester.tap(find.byType(PrimaryButton));
    await tester.pump();
    expect(taps, 0);
  });

  testWidgets('SecondaryButton renders and fires onPressed', (
    WidgetTester tester,
  ) async {
    bool tapped = false;
    await pumpApp(
      tester,
      SecondaryButton(
        label: 'Cancel',
        onPressed: () => tapped = true,
      ),
    );

    expect(find.text('Cancel'), findsOneWidget);
    expect(
      tester.getSize(find.byType(SecondaryButton)).height,
      greaterThanOrEqualTo(48),
    );
    await tester.tap(find.text('Cancel'));
    await tester.pump();
    expect(tapped, isTrue);
  });

  testWidgets('GhostButton renders and fires onPressed', (
    WidgetTester tester,
  ) async {
    bool tapped = false;
    await pumpApp(
      tester,
      GhostButton(
        label: 'Skip for now',
        onPressed: () => tapped = true,
      ),
    );

    expect(find.text('Skip for now'), findsOneWidget);
    await tester.tap(find.text('Skip for now'));
    await tester.pump();
    expect(tapped, isTrue);
  });

  testWidgets('AppCard renders its child inside the double-hairline frame', (
    WidgetTester tester,
  ) async {
    await pumpApp(tester, const AppCard(child: Text('card body')));

    expect(find.text('card body'), findsOneWidget);
    final DecoratedBox frame = tester.widget<DecoratedBox>(
      find
          .descendant(of: find.byType(AppCard), matching: find.byType(DecoratedBox))
          .first,
    );
    final BoxDecoration decoration = frame.decoration as BoxDecoration;
    expect(decoration.color, AppColors.parchment50);
    expect(decoration.border?.top.color, AppColors.parchment400);
    expect(decoration.boxShadow, hasLength(2));
  });

  testWidgets('LabelCaps uppercases its text', (WidgetTester tester) async {
    await pumpApp(tester, const LabelCaps(text: 'eyebrow'));

    expect(find.text('EYEBROW'), findsOneWidget);
  });

  testWidgets('StampBadge shows the stamped text', (WidgetTester tester) async {
    await pumpApp(
      tester,
      const StampBadge(label: 'approved', tone: StampTone.success),
    );

    expect(find.text('APPROVED'), findsOneWidget);
    expect(
      find.descendant(
        of: find.byType(StampBadge),
        matching: find.byType(Transform),
      ),
      findsWidgets,
    );
  });

  testWidgets('StatusChip pairs icon with text and stays >= 28 tall', (
    WidgetTester tester,
  ) async {
    await pumpApp(
      tester,
      const StatusChip(
        label: 'Passed',
        icon: LucideIcons.check,
        tone: StatusTone.success,
      ),
    );

    expect(find.byIcon(LucideIcons.check), findsOneWidget);
    expect(find.text('Passed'), findsOneWidget);
    expect(
      tester.getSize(find.byType(StatusChip)).height,
      greaterThanOrEqualTo(28),
    );
  });

  testWidgets('DashedDivider builds a dashed rule', (WidgetTester tester) async {
    await pumpApp(
      tester,
      const SizedBox(width: 200, child: DashedDivider()),
    );

    expect(find.byType(DashedDivider), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('SkeletonLoader builds across shimmer frames', (
    WidgetTester tester,
  ) async {
    await pumpApp(tester, const SkeletonLoader(width: 60, height: 20));
    await tester.pump(const Duration(milliseconds: 300));
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.byType(SkeletonLoader), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('SkeletonLoader freezes at a static mid-shimmer under reduced '
      'motion (04 §3)', (WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData.dark(useMaterial3: true),
        home: MediaQuery(
          data: const MediaQueryData(disableAnimations: true),
          child: const Scaffold(
            body: Center(child: SkeletonLoader(width: 60, height: 20)),
          ),
        ),
      ),
    );

    Color blockColor() {
      final DecoratedBox box = tester.widget<DecoratedBox>(
        find.descendant(
          of: find.byType(SkeletonLoader),
          matching: find.byType(DecoratedBox),
        ),
      );
      return (box.decoration as BoxDecoration).color!;
    }

    // Static mid-shimmer pose (0.4 → 0.7 at t = 0.5) …
    final Color first = blockColor();
    expect(first.a, moreOrLessEquals(0.55, epsilon: 0.01));

    // … held across frames instead of pulsing.
    await tester.pump(const Duration(milliseconds: 300));
    await tester.pump(const Duration(milliseconds: 300));
    expect(blockColor().toARGB32(), first.toARGB32());
    expect(tester.takeException(), isNull);
  });

  testWidgets('EmptyState renders title, message and action slot', (
    WidgetTester tester,
  ) async {
    await pumpApp(
      tester,
      EmptyState(
        title: 'No images yet',
        message: 'Import a batch to get started.',
        action: GhostButton(label: 'Import', onPressed: () {}),
      ),
    );

    expect(find.text('No images yet'), findsOneWidget);
    expect(find.text('Import a batch to get started.'), findsOneWidget);
    expect(find.byIcon(LucideIcons.imageOff), findsOneWidget);
    expect(find.byType(GhostButton), findsOneWidget);
  });

  testWidgets('ErrorView renders its message and fires Retry', (
    WidgetTester tester,
  ) async {
    bool retried = false;
    await pumpApp(
      tester,
      ErrorView(message: 'Gallery unreachable', onRetry: () => retried = true),
    );

    expect(find.text('Gallery unreachable'), findsOneWidget);
    await tester.tap(find.text('Retry'));
    await tester.pump();
    expect(retried, isTrue);
  });

  testWidgets('StampIn animates to full opacity and the -2deg tilt', (
    WidgetTester tester,
  ) async {
    await pumpApp(tester, const StampIn(child: Text('stamped')));
    expect(opacityAncestors(tester, find.text('stamped')), contains(0.0));

    await tester.pump(const Duration(milliseconds: 400));
    expect(opacityAncestors(tester, find.text('stamped')), contains(1.0));
  });

  testWidgets('StampIn snaps to the final state when reduced motion is on', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData.dark(useMaterial3: true),
        home: MediaQuery(
          data: const MediaQueryData(disableAnimations: true),
          child: const Scaffold(
            body: Center(child: StampIn(child: Text('instant'))),
          ),
        ),
      ),
    );

    expect(opacityAncestors(tester, find.text('instant')), contains(1.0));
  });

  testWidgets('AsyncView folds loading, error and data states', (
    WidgetTester tester,
  ) async {
    await pumpApp(
      tester,
      AsyncView<String>(
        data: AsyncLoading<String>(),
        builder: (String value) => Text(value),
      ),
    );
    expect(find.byType(SkeletonLoader), findsOneWidget);

    bool retried = false;
    await pumpApp(
      tester,
      AsyncView<String>(
        data: AsyncError<String>('boom', StackTrace.current),
        builder: (String value) => Text(value),
        onRetry: () => retried = true,
      ),
    );
    expect(find.byType(ErrorView), findsOneWidget);
    await tester.tap(find.text('Retry'));
    await tester.pump();
    expect(retried, isTrue);

    await pumpApp(
      tester,
      AsyncView<String>(
        data: AsyncData<String>('ready'),
        builder: (String value) => Text(value),
      ),
    );
    expect(find.text('ready'), findsOneWidget);
  });

  testWidgets('showAppToast overlays a toast that auto-dismisses', (
    WidgetTester tester,
  ) async {
    await pumpApp(tester, const SizedBox.shrink());
    showAppToast(
      tester.element(find.byType(Scaffold)),
      'Thumbnail uploaded',
      tone: ToastTone.success,
    );

    await tester.pump();
    await tester.pump(const Duration(milliseconds: 450));
    expect(find.text('Thumbnail uploaded'), findsOneWidget);
    expect(find.text('OK'), findsOneWidget);

    await tester.pump(const Duration(seconds: 3));
    await tester.pump();
    expect(find.text('Thumbnail uploaded'), findsNothing);
  });

  test('thumbnailBasename handles both path separators', () {
    expect(thumbnailBasename('/var/data/photo.jpg'), 'photo.jpg');
    expect(thumbnailBasename(r'C:\assets\render.png'), 'render.png');
    expect(thumbnailBasename(r'mixed\style\frame.webp'), 'frame.webp');
    expect(thumbnailBasename('plain.jpg'), 'plain.jpg');
  });
}
