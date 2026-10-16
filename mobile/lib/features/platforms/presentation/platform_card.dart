import 'package:flutter/material.dart';
import 'package:lucide_flutter/lucide_flutter.dart';

import '../../../app/theme/tokens.dart';
import '../../../core/widgets/app_card.dart';
import '../../../core/widgets/label_caps.dart';
import '../../../core/widgets/status_chip.dart';
import '../../../core/widgets/stamp_in.dart';
import '../domain/platform.dart';

/// One platform tile in the hub grid (05 §2.3): Playfair name, tagline,
/// and an `OPEN` (olive) vs `COMING SOON` (neutral) chip — status carried
/// by text, never color alone (04 §4).
///
/// The whole card is the tap target; the hub decides navigation on tap.
class PlatformCard extends StatelessWidget {
  const PlatformCard({
    super.key,
    required this.platform,
    required this.onTap,
    this.entranceDelay = Duration.zero,
  });

  /// Catalogue entry to render.
  final PlatformEntry platform;

  /// Tap handler — hub routes on [PlatformEntry.available].
  final VoidCallback onTap;

  /// Staggered stamp-in offset for the grid entrance (~60 ms apart).
  final Duration entranceDelay;

  @override
  Widget build(BuildContext context) {
    final TextTheme textTheme = Theme.of(context).textTheme;
    final bool live = platform.available;

    final Widget content = AppCard(
      child: InkWell(
        onTap: onTap,
        borderRadius: const BorderRadius.all(Radius.circular(AppRadii.sm)),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Text(
                    platform.name,
                    style: (textTheme.headlineSmall ?? const TextStyle())
                        .copyWith(
                          color: live ? AppColors.ink800 : AppColors.ink600,
                          fontWeight: FontWeight.w700,
                        ),
                  ),
                ),
                const SizedBox(width: AppSpacing.sm),
                live
                    ? const StatusChip(
                        label: 'OPEN',
                        icon: LucideIcons.circleCheck,
                        tone: StatusTone.success,
                      )
                    : const StatusChip(
                        label: 'COMING SOON',
                        icon: LucideIcons.clock,
                        tone: StatusTone.neutral,
                      ),
              ],
            ),
            const SizedBox(height: AppSpacing.sm),
            Text(
              platform.tagline,
              style: (textTheme.bodySmall ?? const TextStyle()).copyWith(
                color: AppColors.ink400,
                height: 1.43,
              ),
            ),
            const SizedBox(height: AppSpacing.lg),
            Row(
              children: [
                LabelCaps(
                  text: live ? 'Enter the studio' : 'In the works',
                ),
                const SizedBox(width: AppSpacing.sm),
                Icon(
                  LucideIcons.arrowRight,
                  size: 14,
                  color: live ? AppColors.brass400 : AppColors.ink400,
                ),
              ],
            ),
          ],
        ),
      ),
    );

    // Staggered stamp-in entrance (~60 ms apart) — snaps instantly when
    // animations are disabled (StampIn honors disableAnimations itself).
    return StampIn(delay: entranceDelay, child: content);
  }
}
