import 'package:flutter/material.dart';

import 'package:ai_stock_studio/app/theme/tokens.dart';

/// Text-only tertiary action with a transparent background (04 §2).
///
/// Same API and 48 dp touch floor as [PrimaryButton]; the pressed state is an
/// ink wash instead of a fill.
class GhostButton extends StatelessWidget {
  const GhostButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.loading = false,
    this.expanded = false,
  });

  /// Button text; doubles as the semantics label.
  final String label;

  /// Tap callback; `null` disables the button (spinner shows instead).
  final VoidCallback? onPressed;

  /// When true, shows a spinner and blocks taps while work is in flight.
  final bool loading;

  /// When true, stretches the button to the available width.
  final bool expanded;

  static const BorderRadius _kRadius = BorderRadius.all(
    Radius.circular(AppRadii.sm),
  );

  bool get _tappable => onPressed != null && !loading;

  @override
  Widget build(BuildContext context) {
    final bool showSpinner = loading || onPressed == null;
    final TextStyle labelStyle =
        Theme.of(context).textTheme.labelLarge?.copyWith(
              color: AppColors.ink600,
            ) ??
        const TextStyle(color: AppColors.ink600, fontSize: 16);

    final Widget content = Stack(
      alignment: Alignment.center,
      children: [
        Opacity(
          opacity: showSpinner ? 0 : 1,
          child: Text(label, style: labelStyle),
        ),
        if (showSpinner)
          const SizedBox(
            width: 18,
            height: 18,
            child: CircularProgressIndicator(
              strokeWidth: 2,
              valueColor: AlwaysStoppedAnimation<Color>(AppColors.parchment700),
            ),
          ),
      ],
    );

    Widget button = Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: _tappable ? onPressed : null,
        borderRadius: _kRadius,
        highlightColor: AppColors.parchment200,
        splashColor: AppColors.parchment300,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 48),
          child: Padding(
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.lg,
              vertical: AppSpacing.md,
            ),
            child: content,
          ),
        ),
      ),
    );

    if (expanded) {
      button = SizedBox(width: double.infinity, child: button);
    }
    return button;
  }
}
