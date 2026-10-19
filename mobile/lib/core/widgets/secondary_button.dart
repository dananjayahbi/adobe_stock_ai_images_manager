import 'package:flutter/material.dart';

import 'package:ai_stock_studio/app/theme/tokens.dart';

/// Parchment-outlined secondary action (04 §2).
///
/// Same metrics as [PrimaryButton]: 48 dp floor, brass border on press, and
/// a small spinner in place of the label while [loading] or disabled.
class SecondaryButton extends StatefulWidget {
  const SecondaryButton({
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

  @override
  State<SecondaryButton> createState() => _SecondaryButtonState();
}

class _SecondaryButtonState extends State<SecondaryButton> {
  static const BorderRadius _kRadius = BorderRadius.all(
    Radius.circular(AppRadii.sm),
  );

  bool _pressed = false;

  bool get _tappable => widget.onPressed != null && !widget.loading;

  @override
  Widget build(BuildContext context) {
    final bool showSpinner = widget.loading || widget.onPressed == null;
    final Color borderColor = _pressed
        ? AppColors.brass400
        : AppColors.parchment400;
    final TextStyle labelStyle =
        Theme.of(context).textTheme.labelLarge?.copyWith(
              color: AppColors.ink800,
            ) ??
        const TextStyle(color: AppColors.ink800, fontSize: 16);

    final Widget content = Stack(
      alignment: Alignment.center,
      children: [
        Opacity(
          opacity: showSpinner ? 0 : 1,
          child: Text(widget.label, style: labelStyle),
        ),
        if (showSpinner)
          const SizedBox(
            width: 18,
            height: 18,
            child: CircularProgressIndicator(
              strokeWidth: 2,
              valueColor: AlwaysStoppedAnimation<Color>(AppColors.brass400),
            ),
          ),
      ],
    );

    Widget button = AnimatedContainer(
      duration: const Duration(milliseconds: 150),
      curve: Curves.easeInOut,
      decoration: BoxDecoration(
        color: AppColors.parchment200,
        border: Border.all(color: borderColor, width: 1),
        borderRadius: _kRadius,
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: _tappable ? widget.onPressed : null,
          onHighlightChanged: (bool value) => setState(() => _pressed = value),
          borderRadius: _kRadius,
          highlightColor: AppColors.parchment300,
          splashColor: AppColors.parchment400,
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

    if (widget.expanded) {
      button = SizedBox(width: double.infinity, child: button);
    }
    return button;
  }
}
