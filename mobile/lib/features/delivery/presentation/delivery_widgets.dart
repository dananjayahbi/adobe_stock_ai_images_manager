import 'package:flutter/material.dart';
import 'package:lucide_flutter/lucide_flutter.dart';

import '../../../app/theme/tokens.dart';
import '../../../core/widgets/app_card.dart';
import '../../../core/widgets/status_chip.dart';

// Shared presentation atoms for the Delivery screen, split out so
// `delivery_screen.dart` stays under the 400-line screen cap (same move
// dashboard made with `stat_tile.dart`). Owned entirely by the delivery
// feature — no other milestone touches this file.

/// One action card: icon + description + chevron (05 §2.8 layout). Offline
/// disables the tap; [busy] swaps the chevron for a spinner.
class ActionCard extends StatelessWidget {
  const ActionCard({
    super.key,
    required this.icon,
    required this.title,
    required this.caption,
    required this.onTap,
    this.busy = false,
    this.enabled = true,
  });

  final IconData icon;
  final String title;
  final String caption;
  final VoidCallback onTap;
  final bool busy;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AppCard(
      padding: EdgeInsets.zero,
      child: InkWell(
        borderRadius: BorderRadius.circular(AppRadii.md),
        onTap: enabled && !busy ? onTap : null,
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Row(
            children: <Widget>[
              Container(
                width: 40, height: 40,
                decoration: BoxDecoration(
                  color: AppColors.parchment300,
                  borderRadius: BorderRadius.circular(AppRadii.sm),
                ),
                child: Icon(icon, size: 20, color: AppColors.brass400),
              ),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      title,
                      style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600),
                    ),
                    Text(caption, style: theme.textTheme.bodySmall),
                  ],
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              if (enabled && busy)
                const SizedBox(
                  width: 18, height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              else
                const Icon(LucideIcons.chevronRight, size: 20),
            ],
          ),
        ),
      ),
    );
  }
}

/// Stage → chip semantics: delivered = olive, gate-failed = rust,
/// gate-passed awaiting metadata = accent, still processing = neutral.
StatusTone stageTone(String stage) => switch (stage) {
      'METADATA_READY' || 'PUBLISHED' => StatusTone.success,
      'INCOMPATIBLE' || 'OCR_REJECTED' => StatusTone.failure,
      'COMPATIBLE' => StatusTone.accent,
      _ => StatusTone.neutral,
    };

/// Stage → row icon, matching [stageTone]'s families.
IconData stageIcon(String stage) => switch (stage) {
      'METADATA_READY' || 'PUBLISHED' => LucideIcons.circleCheck,
      'INCOMPATIBLE' || 'OCR_REJECTED' => LucideIcons.triangleAlert,
      _ => LucideIcons.clock,
    };
