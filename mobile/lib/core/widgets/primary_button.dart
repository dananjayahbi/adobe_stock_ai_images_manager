import 'package:flutter/material.dart';

import 'package:ai_stock_studio/app/theme/tokens.dart';

/// Oxblood-filled primary call-to-action (04 §2).
///
/// While [loading] is true or [onPressed] is null the label is visually
/// replaced by a small brass spinner, but the label keeps its layout slot so
/// the button never changes width mid-action.
class PrimaryButton extends StatelessWidget {
  const PrimaryButton({
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
    final Color background = onPressed == null
        ? AppColors.oxblood600
        : AppColors.oxblood500;
    final TextStyle labelStyle =
        Theme.of(context).textTheme.labelLarge?.copyWith(
              color: AppColors.ink50,
            ) ??
        const TextStyle(color: AppColors.ink50, fontSize: 16);

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
              valueColor: AlwaysStoppedAnimation<Color>(AppColors.brass300),
            ),
          ),
      ],
    );

    Widget button = AnimatedContainer(
      duration: const Duration(milliseconds: 200),
      curve: Curves.easeInOut,
      decoration: BoxDecoration(
        color: background,
        borderRadius: _kRadius,
      ),
      // Brass "seal" inset ring from the web button (04 §1.3/§2).
      foregroundDecoration: BoxDecoration(
        borderRadius: _kRadius,
        border: Border.all(
          color: AppColors.brass400.withValues(alpha: 0.35),
          width: 1,
        ),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: _tappable ? onPressed : null,
          borderRadius: _kRadius,
          highlightColor: AppColors.oxblood600,
          splashColor: AppColors.oxblood700,
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
      ),
    );

    if (expanded) {
      button = SizedBox(width: double.infinity, child: button);
    }
    return button;
  }
}
