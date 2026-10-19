import 'package:flutter/material.dart';

import 'package:ai_stock_studio/app/theme/tokens.dart';

/// Semantic tone shared with [StampBadge].
enum StatusTone { success, warning, failure, neutral, accent }

/// Small pill pairing a tone-colored icon with text — never color alone
/// (04 §4 rule 1).
class StatusChip extends StatelessWidget {
  const StatusChip({
    super.key,
    required this.label,
    required this.icon,
    required this.tone,
    this.dense = false,
    this.onTap,
  });

  /// Chip text, shown as-is next to the icon.
  final String label;

  /// State icon; always paired with [label].
  final IconData icon;

  /// Color family driving the tinted background, icon and text.
  final StatusTone tone;

  /// Compact variant for dense pill walls (keyword lists, R6): smaller
  /// icon/text and tighter padding — same semantics, less vertical cost.
  final bool dense;

  /// Optional tap handler; the chip grows to a 48 dp touch target when set.
  final VoidCallback? onTap;

  static const BorderRadius _kPill = BorderRadius.all(Radius.circular(999));

  Color get _toneColor => switch (tone) {
        StatusTone.success => AppColors.olive400,
        StatusTone.warning => AppColors.rust400,
        StatusTone.failure => AppColors.rust400,
        StatusTone.neutral => AppColors.parchment700,
        StatusTone.accent => AppColors.oxblood400,
      };

  @override
  Widget build(BuildContext context) {
    final Color color = _toneColor;
    final TextStyle? labelStyle =
        Theme.of(context).textTheme.labelSmall?.copyWith(
              color: color,
              fontSize: dense ? 10 : 11,
              height: 1.2,
              fontWeight: FontWeight.w600,
            );

    Widget body = Padding(
      padding: EdgeInsets.symmetric(
        horizontal: dense ? AppSpacing.xs + 2 : AppSpacing.sm,
        vertical: dense ? 2 : AppSpacing.xs,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: dense ? 12 : 16, color: color),
          SizedBox(width: dense ? 3 : AppSpacing.xs),
          Text(label, style: labelStyle),
        ],
      ),
    );

    if (onTap != null) {
      body = Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          borderRadius: _kPill,
          child: body,
        ),
      );
    }

    return Container(
      constraints: BoxConstraints(
        minHeight: onTap != null ? 48 : (dense ? 22 : 28),
      ),
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: _kPill,
      ),
      child: body,
    );
  }
}
