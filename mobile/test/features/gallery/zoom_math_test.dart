import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ai_stock_studio/features/gallery/presentation/zoom_math.dart';

void main() {
  const Size viewport = Size(400, 600);

  group('zoomAboutFocalPoint (R5 focal anchoring)', () {
    test('keeps the point under the fingers pinned while zooming in', () {
      const Offset focal = Offset(300, 100);
      final Matrix4 result = zoomAboutFocalPoint(
        targetScale: 2.0,
        focalPoint: focal,
        viewport: viewport,
        previousMatrix: Matrix4.identity(),
      );

      // The child point that sat under `focal` stays under `focal`.
      expect(MatrixUtils.transformPoint(result, focal), focal);
      expect(result.getMaxScaleOnAxis(), closeTo(2.0, 1e-9));
    });

    test('pins the focal point through an already-zoomed matrix', () {
      // 1.5× about the origin, then panned — the old double-tap bug source.
      final Matrix4 previous = Matrix4.identity()
        ..scaleByDouble(1.5, 1.5, 1.0, 1.0)
        ..translateByDouble(40.0, -25.0, 0.0, 1.0);
      const Offset focal = Offset(120, 480);

      // The child point currently under the viewport focal point…
      final Offset childUnderFocal = MatrixUtils.transformPoint(
        Matrix4.copy(previous)..invert(),
        focal,
      );

      final Matrix4 result = zoomAboutFocalPoint(
        targetScale: 3.0,
        focalPoint: focal,
        viewport: viewport,
        previousMatrix: previous,
      );

      // …stays under it after the zoom, and the scale target is exact.
      expect(MatrixUtils.transformPoint(result, childUnderFocal), focal);
      expect(result.getMaxScaleOnAxis(), closeTo(3.0, 1e-9));
    });

    test('is NOT a plain origin-anchored scale (regression for the old '
        'scaleByDouble(2) jump)', () {
      const Offset focal = Offset(300, 100);
      final Matrix4 anchored = zoomAboutFocalPoint(
        targetScale: 2.0,
        focalPoint: focal,
        viewport: viewport,
        previousMatrix: Matrix4.identity(),
      );
      final Matrix4 originScaled = Matrix4.identity()
        ..scaleByDouble(2.0, 2.0, 1.0, 1.0);

      expect(
        MatrixUtils.transformPoint(originScaled, focal),
        isNot(MatrixUtils.transformPoint(anchored, focal)),
      );
      // Origin scaling sends the focal point out of frame; anchoring does not.
      expect(
        MatrixUtils.transformPoint(originScaled, focal),
        const Offset(600, 200),
      );
    });

    test('clamps the focal point into the viewport', () {
      const Offset stray = Offset(10_000, -500);
      final Matrix4 result = zoomAboutFocalPoint(
        targetScale: 2.0,
        focalPoint: stray,
        viewport: viewport,
        previousMatrix: Matrix4.identity(),
      );
      const Offset clamped = Offset(400, 0);
      expect(MatrixUtils.transformPoint(result, clamped), clamped);
    });

    test(
      'clamps target scale at fit (1.0) and no-ops at the current scale',
      () {
        final Matrix4 fitted = zoomAboutFocalPoint(
          targetScale: 0.4,
          focalPoint: Offset.zero,
          viewport: viewport,
          previousMatrix: Matrix4.identity(),
        );
        expect(fitted.isIdentity(), isTrue);

        final Matrix4 zoomed = Matrix4.identity()
          ..scaleByDouble(2.0, 2.0, 1.0, 1.0);
        final Matrix4 same = zoomAboutFocalPoint(
          targetScale: 2.0,
          focalPoint: const Offset(10, 10),
          viewport: viewport,
          previousMatrix: zoomed,
        );
        expect(same, zoomed);
      },
    );

    test('doubleTapZoomIn defaults to a clean centered 2.0× about the tap', () {
      // Intrinsic 100% would need the full decode; the documented default
      // is a deterministic 2.0× (authed_image_view.dart).
      final Matrix4 inMatrix = doubleTapZoomIn(
        focalPoint: const Offset(50, 550),
        viewport: viewport,
        previousMatrix: Matrix4.identity(),
      );
      expect(inMatrix.getMaxScaleOnAxis(), closeTo(2.0, 1e-9));
      expect(
        MatrixUtils.transformPoint(inMatrix, const Offset(50, 550)),
        const Offset(50, 550),
      );
    });

    test(
      'doubleTapZoomOut returns to FIT (identity) and isZoomed tracks it',
      () {
        expect(doubleTapZoomOut().isIdentity(), isTrue);

        expect(isZoomed(Matrix4.identity()), isFalse);
        expect(
          isZoomed(Matrix4.identity()..scaleByDouble(1.005, 1.005, 1.0, 1.0)),
          isFalse, // inside the 1.01 float-noise epsilon
        );
        expect(
          isZoomed(Matrix4.identity()..scaleByDouble(1.02, 1.02, 1.0, 1.0)),
          isTrue,
        );
      },
    );
  });

  group('clampCoverage + panBy (R8 pinch)', () {
    test('at fit the coverage range collapses to zero translation', () {
      final Matrix4 panned = panBy(
        previousMatrix: Matrix4.identity(),
        delta: const Offset(30, -12),
        viewport: viewport,
      );
      expect(panned.storage[12], 0.0);
      expect(panned.storage[13], 0.0);
    });

    test('pans while zoomed but stops at the coverage edge', () {
      final Matrix4 zoomed = Matrix4.identity()
        ..scaleByDouble(2.0, 2.0, 1.0, 1.0);
      // In range: 400·(1−2) = −400 ≤ tx ≤ 0, 600·(1−2) = −600 ≤ ty ≤ 0.
      final Matrix4 moved = panBy(
        previousMatrix: zoomed,
        delta: const Offset(-100, -50),
        viewport: viewport,
      );
      expect(moved.storage[12], closeTo(-100, 1e-9));
      expect(moved.storage[13], closeTo(-50, 1e-9));

      // Far beyond: clamped to the edge that still covers the viewport.
      final Matrix4 clampedX = panBy(
        previousMatrix: zoomed,
        delta: const Offset(-1000, 0),
        viewport: viewport,
      );
      expect(clampedX.storage[12], closeTo(-400, 1e-9));
      final Matrix4 clampedY = panBy(
        previousMatrix: zoomed,
        delta: const Offset(0, 500),
        viewport: viewport,
      );
      expect(clampedY.storage[13], 0.0);
    });

    test('clampCoverage leaves an in-range matrix untouched', () {
      final Matrix4 zoomed = Matrix4.identity()
        ..scaleByDouble(2.0, 2.0, 1.0, 1.0)
        ..translateByDouble(-40.0, -60.0, 0.0, 1.0);
      final Matrix4 result = clampCoverage(matrix: zoomed, viewport: viewport);
      expect(identical(result, zoomed), isTrue);
    });
  });
}
