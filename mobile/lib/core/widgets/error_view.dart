import 'package:flutter/material.dart';
import 'package:lucide_flutter/lucide_flutter.dart';

import 'package:ai_stock_studio/app/theme/tokens.dart';
import 'secondary_button.dart';

/// Inline error block: rust icon, message and an optional Retry action
/// (04 §2). Announced via a semantics live region (04 §4).
class ErrorView extends StatelessWidget {
  const ErrorView({super.key, this.message, this.onRetry});

  /// Failure copy; falls back to a generic line when null.
  final String? message;

  /// Wired to the Retry button when provided.
  final VoidCallback? onRetry;

  static const String _kFallbackMessage = 'Something went wrong.';

  @override
  Widget build(BuildContext context) {
    final TextTheme textTheme = Theme.of(context).textTheme;
    return Semantics(
      liveRegion: true,
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(
                LucideIcons.circleAlert,
                size: 32,
                color: AppColors.rust400,
              ),
              const SizedBox(height: AppSpacing.md),
              Text(
                message ?? _kFallbackMessage,
                textAlign: TextAlign.center,
                style: textTheme.bodyMedium?.copyWith(
                  color: AppColors.ink800,
                  height: 1.5,
                ),
              ),
              if (onRetry != null) ...[
                const SizedBox(height: AppSpacing.lg),
                SecondaryButton(label: 'Retry', onPressed: onRetry),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
