/// Pure matrix math for the detail viewer's gestures (R5).
///
/// Kept free of widgets so the focal-point anchoring can be unit-tested
/// directly: the old double-tap built `Matrix4.identity()..scaleByDouble(2)`
/// which anchors at the **origin** (top-left) — content jumped out from
/// under the finger. Every zoom the app applies goes through
/// [zoomAboutFocalPoint].
library;

import 'package:flutter/material.dart';

/// Matrix that scales the content so its axis scale becomes [targetScale],
/// keeping the child-space point currently under [focalPoint] (viewport
/// coordinates) pinned under that same viewport point.
///
/// Construction: `T(f) · S(k) · T(-f) · previousMatrix` where
/// `k = targetScale / previousScale`. A viewport point `f` maps back to
/// itself: `previousMatrix · (previousMatrix⁻¹ f) = f`, the inner
/// translations cancel, so the zoomed point is exactly `f`.
///
/// [viewport] clamps [focalPoint] into the visible area so a stray gesture
/// coordinate can never drag the image off-screen. [targetScale] is clamped
/// to `>= 1.0` — below fit there is empty space around a contain-fit image.
Matrix4 zoomAboutFocalPoint({
  required double targetScale,
  required Offset focalPoint,
  required Size viewport,
  required Matrix4 previousMatrix,
}) {
  final double previousScale =
      previousMatrix.getMaxScaleOnAxis().clamp(1.0, double.infinity);
  final double scale = targetScale.clamp(1.0, double.infinity);
  final double factor = scale / previousScale;

  final Offset focal = Offset(
    focalPoint.dx.clamp(0.0, viewport.width),
    focalPoint.dy.clamp(0.0, viewport.height),
  );

  if (factor == 1.0) {
    return previousMatrix.clone();
  }
  return Matrix4.identity()
    ..translateByDouble(focal.dx, focal.dy, 0.0, 1.0)
    ..scaleByDouble(factor, factor, 1.0, 1.0)
    ..translateByDouble(-focal.dx, -focal.dy, 0.0, 1.0)
    ..multiply(previousMatrix);
}

/// Double-tap zoom-in target: [zoomAboutFocalPoint] to [onTapScale]
/// (default 2.0×) about the tap point, from whatever the matrix is now.
Matrix4 doubleTapZoomIn({
  required Offset focalPoint,
  required Size viewport,
  required Matrix4 previousMatrix,
  double onTapScale = 2.0,
}) =>
    zoomAboutFocalPoint(
      targetScale: onTapScale,
      focalPoint: focalPoint,
      viewport: viewport,
      previousMatrix: previousMatrix,
    );

/// Double-tap zoom-out target: back to FIT — plain identity, the
/// `alignment: Alignment.center` resting position of [InteractiveViewer].
/// The pan accumulated while zoomed collapses cleanly to center.
Matrix4 doubleTapZoomOut() => Matrix4.identity();

/// Whether [matrix] counts as zoomed for the toggle + pager-physics gate
/// (matches the viewer's `> 1.01` epsilon against float noise).
bool isZoomed(Matrix4 matrix) => matrix.getMaxScaleOnAxis() > 1.01;
