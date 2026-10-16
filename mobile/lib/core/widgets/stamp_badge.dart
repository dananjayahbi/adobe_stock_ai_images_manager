import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import 'package:ai_stock_studio/app/theme/tokens.dart';

/// Semantic tone for [StampBadge] and [StatusChip] styling.
enum StampTone { success, warning, failure, neutral, accent }

/// Rotated dashed postmark stamp (04 §2, web `.stamp`).
class StampBadge extends StatelessWidget {
  const StampBadge({
    super.key,
    required this.label,
    required this.tone,
    this.rotation = -4,
  });

  /// Stamp text; rendered uppercase, announced in original case.
  final String label;

  /// Color family driving the dashed ring and text.
  final StampTone tone;

  /// Rotation in degrees; the web stamp sits at -4°.
  final double rotation;

  Color get _toneColor => switch (tone) {
        StampTone.success => AppColors.olive400,
        StampTone.warning => AppColors.rust400,
        StampTone.failure => AppColors.rust400,
        StampTone.neutral => AppColors.parchment700,
        StampTone.accent => AppColors.oxblood400,
      };

  @override
  Widget build(BuildContext context) {
    final Color color = _toneColor;
    return Transform.rotate(
      angle: rotation * math.pi / 180,
      child: CustomPaint(
        painter: _StampRingPainter(color: color),
        child: Padding(
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.md,
            vertical: AppSpacing.xs,
          ),
          child: Text(
            label.toUpperCase(),
            semanticsLabel: label,
            style: GoogleFonts.specialElite(
              fontSize: 12,
              height: 1.2,
              letterSpacing: 0.2 * 12,
              color: color,
            ),
          ),
        ),
      ),
    );
  }
}

/// Dashed 2 px stadium ring drawn around the stamp text.
class _StampRingPainter extends CustomPainter {
  const _StampRingPainter({required this.color});

  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    if (size.isEmpty) {
      return;
    }
    final RRect rect = RRect.fromRectAndRadius(
      Offset.zero & size,
      Radius.circular(size.shortestSide / 2),
    );
    final Path path = Path()..addRRect(rect);
    final Paint paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2;
    for (final metric in path.computeMetrics()) {
      double distance = 0;
      while (distance < metric.length) {
        canvas.drawPath(metric.extractPath(distance, distance + 6), paint);
        distance += 10; // 6 px dash, 4 px gap.
      }
    }
  }

  @override
  bool shouldRepaint(_StampRingPainter oldDelegate) =>
      oldDelegate.color != color;
}
