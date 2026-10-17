import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:ai_stock_studio/app/theme/theme.dart';
import 'package:ai_stock_studio/core/network/session_cookie.dart';
import 'package:ai_stock_studio/features/gallery/domain/image_record.dart';
import 'package:ai_stock_studio/features/gallery/presentation/authed_image_view.dart';
import 'package:ai_stock_studio/features/gallery/presentation/zoom_math.dart';
import 'package:ai_stock_studio/features/settings/data/profile_store.dart';

ImageRecord _record() => const ImageRecord(
  id: 'r1',
  filename: 'wire_loop.jpg',
  status: 'PASSED',
  state: 'APPROVED',
);

/// The viewer's on-screen matrix (`alignment: null` ⇒ pixels == matrix 1:1).
Matrix4 matrixOf(WidgetTester tester) => tester
    .widget<Transform>(find.byKey(const ValueKey('authed-image-matrix')))
    .transform;

void main() {
  setUpAll(() {
    GoogleFonts.config.allowRuntimeFetching = false;
    SharedPreferences.setMockInitialValues(<String, Object>{});
    TestWidgetsFlutterBinding.ensureInitialized();
  });

  /// Pumps one [AuthedImageView] page and records zoom crossings.
  Future<List<bool>> pumpView(WidgetTester tester) async {
    final List<bool> zoomEvents = <bool>[];
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [sharedPreferencesProvider.overrideWithValue(prefs)],
        child: MaterialApp(
          theme: buildAppTheme(),
          home: Scaffold(
            body: AuthedImageView(
              record: _record(),
              onZoomChanged: zoomEvents.add,
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    return zoomEvents;
  }

  /// Synthesised double tap (flutter_test ships no doubleTap helper):
  /// two taps ≥ kDoubleTapMinTime (40 ms) apart yet inside the 300 ms
  /// deadline the recognizer holds between them.
  Future<void> doubleTapAt(WidgetTester tester, Finder finder) async {
    final Offset at = tester.getCenter(finder);
    final TestGesture first = await tester.startGesture(at);
    await first.up();
    await tester.pump(const Duration(milliseconds: 100));
    final TestGesture second = await tester.startGesture(at);
    await second.up();
    await tester.pump(const Duration(milliseconds: 60));
  }

  testWidgets('double-tap toggles FIT ↔ 2.0× about the tap, never from the '
      'origin (R5)', (WidgetTester tester) async {
    final List<bool> zoomEvents = await pumpView(tester);

    expect(matrixOf(tester).isIdentity(), isTrue);
    expect(zoomEvents, isEmpty);

    // First double-tap: zoom IN (documented default: clean 2.0× about the
    // tap point — intrinsic 100% needs the full decode).
    await doubleTapAt(tester, find.byType(AuthedImageView));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(matrixOf(tester).getMaxScaleOnAxis(), closeTo(2.0, 0.01));
    expect(isZoomed(matrixOf(tester)), isTrue);
    expect(zoomEvents, <bool>[true]);

    // Content must not have jumped from the top-left: the tapped point
    // (center of the viewport) maps to itself, not to 2× its coordinates.
    final Offset center = Offset(
      tester.getSize(find.byType(AuthedImageView)).width / 2,
      tester.getSize(find.byType(AuthedImageView)).height / 2,
    );
    expect(
      MatrixUtils.transformPoint(matrixOf(tester), center),
      center,
      reason: 'zoom must stay under the fingers, not anchor at the origin',
    );

    // Second double-tap: back to FIT (identity).
    expect(
      matrixOf(tester).getMaxScaleOnAxis(),
      closeTo(2.0, 0.01),
      reason: 'still zoomed in when the second double-tap arrives',
    );
    await doubleTapAt(tester, find.byType(AuthedImageView));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(zoomEvents, <bool>[true, false]);
    expect(matrixOf(tester).isIdentity(), isTrue);
  });

  testWidgets('detail image request carries the session Cookie header '
      '(R7b)', (WidgetTester tester) async {
    await pumpView(tester);

    final CachedNetworkImage cold = tester.widget(
      find.byType(CachedNetworkImage),
    );
    expect(
      cold.httpHeaders?['Cookie'],
      isNull, // cold start: no session published yet
    );

    // Publish the stored session the way auth_cookie_jar does on replay…
    final ProviderContainer container = ProviderScope.containerOf(
      tester.element(find.byType(AuthedImageView)),
    );
    container
        .read(sessionCookieHeaderProvider.notifier)
        .set('studio_session=abc123');
    await tester.pump();

    // …and the loader rebuilds with the explicit header (mirrors the
    // thumbnail.dart pattern — no header → 401 on uncached images).
    final CachedNetworkImage warm = tester.widget(
      find.byType(CachedNetworkImage),
    );
    expect(warm.httpHeaders?['Cookie'], 'studio_session=abc123');
    expect(warm.fit, BoxFit.contain);
  });

  /// Pinch repro (R8): spread two pointers around a point and verify the
  /// scene content that was under the fingers STAYS under them — the user
  /// reports the pinch anchors toward a corner on device.
  testWidgets('pinch scales about the focal point, not a corner (R8)', (
    WidgetTester tester,
  ) async {
    await pumpView(tester);

    expect(matrixOf(tester).isIdentity(), isTrue);

    // Off-center focal: 75% right, 25% down — catches any origin drift
    // that a center-focal gesture would mask.
    final Size size = tester.getSize(find.byType(AuthedImageView));
    final Offset focal = Offset(size.width * 0.75, size.height * 0.25);
    // The scene point currently under the focal (identity matrix → same).
    final Offset sceneUnderFocal = MatrixUtils.transformPoint(
      Matrix4.inverted(matrixOf(tester)),
      focal,
    );

    final TestGesture g1 = await tester.startGesture(
      focal - const Offset(50, 0),
    );
    final TestGesture g2 = await tester.startGesture(
      focal + const Offset(50, 0),
    );
    await tester.pump();
    for (int i = 1; i <= 6; i++) {
      await g1.moveTo(focal - Offset(50 + i * 20, 0));
      await g2.moveTo(focal + Offset(50 + i * 20, 0));
      await tester.pump(const Duration(milliseconds: 16));
    }
    await g1.up();
    await g2.up();
    await tester.pump(const Duration(milliseconds: 300));

    // Spread 50 → 170 px half-width ⇒ ~3.4× (within min 1 / max 4).
    final double scale = matrixOf(tester).getMaxScaleOnAxis();
    expect(scale, greaterThan(2.0));

    // THE invariant: the content point that was under the fingers is still
    // under the (unchanged) focal after the whole gesture.
    final Offset rendered = MatrixUtils.transformPoint(
      matrixOf(tester),
      sceneUnderFocal,
    );
    expect(
      rendered.dx,
      closeTo(focal.dx, 1.0),
      reason:
          'x drifted to ${rendered.dx} (focal ${focal.dx}) — '
          'zoom is anchoring away from the fingers',
    );
    expect(
      rendered.dy,
      closeTo(focal.dy, 1.0),
      reason: 'y drifted to ${rendered.dy} (focal ${focal.dy})',
    );
  });
}
