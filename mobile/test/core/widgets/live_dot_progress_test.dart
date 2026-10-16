import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ai_stock_studio/app/theme/tokens.dart';
import 'package:ai_stock_studio/core/widgets/live_dot.dart';
import 'package:ai_stock_studio/core/widgets/progress_bar.dart';

Widget _host(Widget child, {bool disableAnimations = false}) {
  return MaterialApp(
    home: MediaQuery(
      // Inner MediaQuery wins over MaterialApp's view-derived one, so the
      // reduced-motion branches are testable.
      data: MediaQueryData(disableAnimations: disableAnimations),
      child: Scaffold(body: Center(child: child)),
    ),
  );
}

Finder _fillOf(Finder bar) => find.descendant(
      of: bar,
      matching: find.byWidgetPredicate(
        (Widget w) => w is ColoredBox && w.color == AppColors.brass400,
      ),
    );

Finder _trackOf(Finder bar) => find.descendant(
      of: bar,
      matching: find.byWidgetPredicate(
        (Widget w) => w is ColoredBox && w.color == AppColors.parchment200,
      ),
    );

void main() {
  group('LiveDot', () {
    testWidgets('renders 8 dp brass dot + label-caps, liveRegion announced', (
      WidgetTester tester,
    ) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      await tester.pumpWidget(
        _host(const LiveDot(label: 'RUNNING')),
      );
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('RUNNING'), findsOneWidget);

      final Finder dot = find.descendant(
        of: find.byType(LiveDot),
        matching: find.byType(DecoratedBox),
      );
      expect(tester.getSize(dot).width, 8);
      expect(tester.getSize(dot).height, 8);

      final SemanticsNode node = tester.getSemantics(find.byType(LiveDot));
      expect(
        node.getSemanticsData().flagsCollection.isLiveRegion,
        isTrue,
      );

      handle.dispose();
    });

    testWidgets('pulses opacity across the 1200 ms loop', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_host(const LiveDot()));
      await tester.pump();

      final Finder dotOpacity = find.descendant(
        of: find.byType(LiveDot),
        matching: find.byType(Opacity),
      );
      final double atStart =
          tester.widget<Opacity>(dotOpacity).opacity;

      await tester.pump(const Duration(milliseconds: 600));
      final double midway = tester.widget<Opacity>(dotOpacity).opacity;

      expect(midway, isNot(closeTo(atStart, 0.01)));
    });

    testWidgets('reduced motion freezes the pulse', (WidgetTester tester) async {
      await tester.pumpWidget(_host(const LiveDot(), disableAnimations: true));
      await tester.pump();

      final Finder dotOpacity = find.descendant(
        of: find.byType(LiveDot),
        matching: find.byType(Opacity),
      );
      final double atStart = tester.widget<Opacity>(dotOpacity).opacity;
      await tester.pump(const Duration(milliseconds: 600));
      final double later = tester.widget<Opacity>(dotOpacity).opacity;

      expect(later, atStart);
    });

    testWidgets('enabled=false keeps the dot static', (WidgetTester tester) async {
      await tester.pumpWidget(_host(const LiveDot(enabled: false)));
      await tester.pump();

      final Finder dotOpacity = find.descendant(
        of: find.byType(LiveDot),
        matching: find.byType(Opacity),
      );
      final double atStart = tester.widget<Opacity>(dotOpacity).opacity;
      await tester.pump(const Duration(milliseconds: 600));
      expect(tester.widget<Opacity>(dotOpacity).opacity, atStart);
    });
  });

  group('ProgressBar', () {
    testWidgets('determinate: brass fill width follows value + semantics', (
      WidgetTester tester,
    ) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      await tester.pumpWidget(
        _host(
          SizedBox(
            width: 200,
            child: ProgressBar(value: 0.25, height: 6),
          ),
        ),
      );
      await tester.pump();

      final Finder bar = find.byType(ProgressBar);
      expect(tester.getSize(bar).height, 6);
      expect(tester.getSize(_trackOf(bar)).width, 200);

      final Finder fill = _fillOf(bar);
      expect(tester.getSize(fill).width, 50); // 200 * 0.25
      expect(tester.getSize(fill).height, 6);

      expect(tester.getSemantics(bar).value, '25%');
      handle.dispose();
    });

    testWidgets('determinate clamps out-of-range values', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        _host(
          SizedBox(
            width: 200,
            child: ProgressBar(value: 1.8),
          ),
        ),
      );
      await tester.pump();

      expect(tester.getSize(_fillOf(find.byType(ProgressBar))).width, 200);
    });

    testWidgets('indeterminate slides a brass segment', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        _host(SizedBox(width: 200, child: ProgressBar())),
      );
      await tester.pump();

      final Finder fill = _fillOf(find.byType(ProgressBar));
      expect(tester.getSize(fill).width, 70); // 35 % of 200
      final Offset start = tester.getTopLeft(fill);

      await tester.pump(const Duration(milliseconds: 300));
      final Offset moved = tester.getTopLeft(_fillOf(find.byType(ProgressBar)));

      expect(moved.dx, greaterThan(start.dx));
    });

    testWidgets('indeterminate parks centered under reduced motion', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        _host(
          SizedBox(
            width: 200,
            child: ProgressBar(),
          ),
          disableAnimations: true,
        ),
      );
      await tester.pump();

      final Finder fill = _fillOf(find.byType(ProgressBar));
      final Finder bar = find.byType(ProgressBar);
      expect(tester.getSize(fill).width, 70); // (200 - 70) / 2
      // Centered both inside the 200 dp bar and by the test host's Center.
      expect(
        tester.getTopLeft(fill).dx,
        tester.getTopLeft(bar).dx + 65,
      );

      await tester.pump(const Duration(milliseconds: 400));
      final Finder parked = _fillOf(find.byType(ProgressBar));
      expect(
        tester.getTopLeft(parked).dx,
        tester.getTopLeft(find.byType(ProgressBar)).dx + 65,
      );
    });
  });
}
