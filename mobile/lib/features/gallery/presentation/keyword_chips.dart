import 'package:flutter/material.dart';

import '../../../app/theme/tokens.dart';

/// Dense keyword pill for the metadata sheet's keyword wall (05 §2.6).
///
/// Deliberately content-sized: the outer box carries **no** [Alignment],
/// so inside a [Wrap] it hugs its label. An alignment-bearing container
/// expands to the incoming maxWidth — inside a [Wrap] that means one
/// full-width chip per run, i.e. one keyword per line stacking down the
/// drawer (the bug this widget replaces, see R6).
///
/// Brass hairline styling matches the vintage dark theme: faint brass
/// fill, 1 px brass rule, brass label.
class KeywordChip extends StatelessWidget {
  const KeywordChip({super.key, required this.label});

  /// Keyword text — rendered in full, never truncated.
  final String label;

  static const BorderRadius _kRadius = BorderRadius.all(
    Radius.circular(999),
  );

  /// 11 px label — small enough for a wall of chips, still legible.
  static const double _kFontSize = 11;

  /// Tight horizontal inset (6–8 dp band) so several chips fit per run.
  static const double _kHorizontalPadding = 7;

  static const double _kVerticalPadding = 3;

  @override
  Widget build(BuildContext context) {
    final TextStyle style =
        Theme.of(context).textTheme.labelSmall?.copyWith(
              color: AppColors.brass300,
              fontSize: _kFontSize,
              height: 1.2,
              fontWeight: FontWeight.w600,
            ) ??
        const TextStyle(
          color: AppColors.brass300,
          fontSize: _kFontSize,
          height: 1.2,
          fontWeight: FontWeight.w600,
        );

    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.brass500.withValues(alpha: 0.14),
        border: Border.all(
          color: AppColors.brass600.withValues(alpha: 0.85),
          width: 1,
        ),
        borderRadius: _kRadius,
      ),
      child: Padding(
        padding: EdgeInsets.symmetric(
          horizontal: _kHorizontalPadding,
          vertical: _kVerticalPadding,
        ),
        child: Text(label, style: style),
      ),
    );
  }
}

/// Compact flow layout for a record's full keyword list — every keyword
/// rendered, wrapping across as many short runs as needed. No truncation
/// and no "show more" cutoff; density comes from content-sized pills and
/// tight 5 dp gaps rather than from dropping keywords.
class KeywordChips extends StatelessWidget {
  const KeywordChips({super.key, required this.keywords});

  /// All generated keywords; every one is rendered exactly once.
  final List<String> keywords;

  /// Gap between chips in a run and between runs (4–6 dp band).
  static const double _kGap = 5;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: _kGap,
      runSpacing: _kGap,
      children: <Widget>[
        for (final String keyword in keywords)
          KeywordChip(label: keyword),
      ],
    );
  }
}
