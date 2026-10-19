import 'package:flutter/material.dart';

import 'package:ai_stock_studio/app/theme/tokens.dart';

/// 1 px dashed horizontal rule — the ticket perforation (04 §2).
class DashedDivider extends StatelessWidget {
  const DashedDivider({super.key, this.height});

  /// Total widget height; defaults to the 1 px rule itself.
  final double? height;

  @override
  Widget build(BuildContext context) {
    final double ruleHeight = height ?? 1;
    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints constraints) {
        final double width = constraints.maxWidth.isFinite
            ? constraints.maxWidth
            : 0;
        return CustomPaint(
          size: Size(width, ruleHeight),
          painter: const _DashPainter(),
        );
      },
    );
  }
}

/// Draws a 4/4 dash pattern in `parchment-400`.
class _DashPainter extends CustomPainter {
  const _DashPainter();

  static const double _dash = 4;
  static const double _gap = 4;

  @override
  void paint(Canvas canvas, Size size) {
    if (size.width <= 0) {
      return;
    }
    final Paint paint = Paint()
      ..color = AppColors.parchment400
      ..strokeWidth = 1
      ..style = PaintingStyle.stroke;
    final double y = size.height / 2;
    double x = 0;
    while (x < size.width) {
      final double end = x + _dash < size.width ? x + _dash : size.width;
      canvas.drawLine(Offset(x, y), Offset(end, y), paint);
      x += _dash + _gap;
    }
  }

  @override
  bool shouldRepaint(_DashPainter oldDelegate) => false;
}
