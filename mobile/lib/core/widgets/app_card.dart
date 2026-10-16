import 'package:flutter/material.dart';

import 'package:ai_stock_studio/app/theme/tokens.dart';

/// Signature double-hairline card frame (04 §2, web `.frame-card`).
///
/// Outer 1 px `parchment-400` border, 3 px gap, then the inset double rule
/// (1 px light + 4 px dark, matching the web boxShadow), `parchment-50` fill
/// and the warm `card` shadow.
class AppCard extends StatelessWidget {
  const AppCard({super.key, required this.child, this.padding});

  /// Card content.
  final Widget child;

  /// Content padding; defaults to [AppSpacing.lg].
  final EdgeInsetsGeometry? padding;

  static const BorderRadius _kRadius = BorderRadius.all(
    Radius.circular(AppRadii.sm),
  );

  static const List<BoxShadow> _kShadow = [
    BoxShadow(color: Color(0x73000000), offset: Offset(0, 1), blurRadius: 2),
    BoxShadow(
      color: Color(0xB3000000),
      offset: Offset(0, 8),
      blurRadius: 24,
      spreadRadius: -16,
    ),
  ];

  @override
  Widget build(BuildContext context) {
    // Container (not DecoratedBox) so the 1 px border insets the inner rules
    // exactly like the web frame: border -> light hairline -> dark inset.
    return Container(
      decoration: BoxDecoration(
        color: AppColors.parchment50,
        border: Border.all(color: AppColors.parchment400, width: 1),
        borderRadius: _kRadius,
        boxShadow: _kShadow,
      ),
      child: DecoratedBox(
        // Light hairline painted on top of the dark inset (web layering).
        decoration: BoxDecoration(
          borderRadius: _kRadius,
          border: Border.all(
            color: AppColors.ink800.withValues(alpha: 0.06),
            width: 1,
          ),
        ),
        position: DecorationPosition.foreground,
        child: DecoratedBox(
          decoration: BoxDecoration(
            borderRadius: _kRadius,
            border: Border.all(
              color: Colors.black.withValues(alpha: 0.18),
              width: 4,
            ),
          ),
          position: DecorationPosition.foreground,
          child: Padding(
            padding: padding ?? const EdgeInsets.all(AppSpacing.lg),
            child: child,
          ),
        ),
      ),
    );
  }
}
