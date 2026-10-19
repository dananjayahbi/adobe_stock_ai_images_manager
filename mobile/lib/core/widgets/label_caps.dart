import 'package:flutter/material.dart';

import 'package:ai_stock_studio/app/theme/tokens.dart';

/// 11 px uppercase letterspaced eyebrow label (04 §1.2, web `.label-caps`).
class LabelCaps extends StatelessWidget {
  const LabelCaps({super.key, required this.text});

  /// Raw label text; rendered uppercased, announced in original case.
  final String text;

  static const double _kFontSize = 11;

  @override
  Widget build(BuildContext context) {
    final TextStyle base =
        Theme.of(context).textTheme.labelSmall ?? const TextStyle();
    return Text(
      text.toUpperCase(),
      semanticsLabel: text,
      style: base.copyWith(
        fontSize: _kFontSize,
        height: 1.2,
        // Flutter letterSpacing is pixels; 0.18em at 11px.
        letterSpacing: 0.18 * _kFontSize,
        color: AppColors.ink400,
        fontWeight: FontWeight.w600,
      ),
    );
  }
}
