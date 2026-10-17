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
        overrides: [
          sharedPreferencesProvider.overrideWithValue(prefs),
        ],
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

    final InteractiveViewer viewer = tester.widget(find.byType(InteractiveViewer));
    final TransformationController controller = viewer.transformationController!;
    expect(controller.value.isIdentity(), isTrue);
    expect(zoomEvents, isEmpty);

    // First double-tap: zoom IN (documented default: clean 2.0× about the
    // tap point — intrinsic 100% needs the full decode).
    await doubleTapAt(tester, find.byType(AuthedImageView));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(controller.value.getMaxScaleOnAxis(), closeTo(2.0, 0.01));
    expect(isZoomed(controller.value), isTrue);
    expect(zoomEvents, <bool>[true]);

    // Content must not have jumped from the top-left: the tapped point
    // (center of the viewport) maps to itself, not to 2× its coordinates.
    final Offset center = Offset(
      tester.getSize(find.byType(AuthedImageView)).width / 2,
      tester.getSize(find.byType(AuthedImageView)).height / 2,
    );
    expect(
      MatrixUtils.transformPoint(controller.value, center),
      center,
      reason: 'zoom must stay under the fingers, not anchor at the origin',
    );

    // Second double-tap: back to FIT (identity).
    expect(
      controller.value.getMaxScaleOnAxis(),
      closeTo(2.0, 0.01),
      reason: 'still zoomed in when the second double-tap arrives',
    );
    await doubleTapAt(tester, find.byType(AuthedImageView));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(zoomEvents, <bool>[true, false]);
    expect(controller.value.isIdentity(), isTrue);
  });

  testWidgets('detail image request carries the session Cookie header '
      '(R7b)', (WidgetTester tester) async {
    await pumpView(tester);

    final CachedNetworkImage cold =
        tester.widget(find.byType(CachedNetworkImage));
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
    final CachedNetworkImage warm =
        tester.widget(find.byType(CachedNetworkImage));
    expect(warm.httpHeaders?['Cookie'], 'studio_session=abc123');
    expect(warm.fit, BoxFit.contain);
  });
}
