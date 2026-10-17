import 'package:flutter/material.dart';

import '../../../app/theme/tokens.dart';
import '../../../core/widgets/app_card.dart';
import '../../../core/widgets/label_caps.dart';
import '../../../core/widgets/skeleton_loader.dart';
import '../../../core/widgets/status_chip.dart';

/// Compact stat card for the dashboard's 2-column stats grid (05 §2.4):
/// Playfair value tinted by a semantic [StatusTone], label-caps caption,
/// optional chip
/// (04 §1.2/§4 — never color alone when a chip is attached).
class StatTile extends StatelessWidget {
  const StatTile({
    super.key,
    required this.value,
    required this.label,
    required this.tone,
    this.chip,
  });

  /// Formatted headline number, e.g. `'161'`.
  final String value;

  /// label-caps caption under the value.
  final String label;

  /// Accent driving the value color.
  final StatusTone tone;

  /// Optional status pill under the label.
  final StatusChip? chip;

  Color get _accent => switch (tone) {
        StatusTone.success => AppColors.olive400,
        StatusTone.warning => AppColors.rust400,
        StatusTone.failure => AppColors.rust400,
        StatusTone.accent => AppColors.oxblood400,
        StatusTone.neutral => AppColors.ink800,
      };

  @override
  Widget build(BuildContext context) {
    return AppCard(
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            value,
            style: Theme.of(context).textTheme.headlineLarge?.copyWith(
                  fontSize: 26,
                  color: _accent,
                ),
          ),
          const SizedBox(height: AppSpacing.xs),
          LabelCaps(text: label),
          if (chip != null) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            chip!,
          ],
        ],
      ),
    );
  }
}

/// Loading twin of [StatTile] for the dashboard's 2-column stats grid
/// (05 §2.4 loading state). Skeletons live beside the tiles they stand in
/// for so the screen itself stays inside the 400-line rule.
class StatTileSkeleton extends StatelessWidget {
  const StatTileSkeleton({super.key});

  @override
  Widget build(BuildContext context) {
    return const AppCard(
      padding: EdgeInsets.all(AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.center,
        children: <Widget>[
          SkeletonLoader(
            width: 64,
            height: 26,
            radius: BorderRadius.all(Radius.circular(AppRadii.sm)),
          ),
          SizedBox(height: AppSpacing.sm),
          SkeletonLoader(
            width: 96,
            height: 12,
            radius: BorderRadius.all(Radius.circular(AppRadii.sm)),
          ),
        ],
      ),
    );
  }
}

/// 8-tile skeleton mirroring the loaded Latest grid (05 §2.4).
class LatestGridSkeleton extends StatelessWidget {
  const LatestGridSkeleton({super.key});

  @override
  Widget build(BuildContext context) {
    return GridView.count(
      crossAxisCount: 2,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      mainAxisSpacing: AppSpacing.md,
      crossAxisSpacing: AppSpacing.md,
      childAspectRatio: 1,
      children: <Widget>[
        for (int i = 0; i < 8; i++)
          const SkeletonLoader(
            radius: BorderRadius.all(Radius.circular(AppRadii.sm)),
          ),
      ],
    );
  }
}

/// Loading twin of the running-job card: name row + bar.
class RunningJobSkeleton extends StatelessWidget {
  const RunningJobSkeleton({super.key});

  @override
  Widget build(BuildContext context) {
    return const Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        SkeletonLoader(
          width: 160,
          height: 18,
          radius: BorderRadius.all(Radius.circular(AppRadii.sm)),
        ),
        SizedBox(height: AppSpacing.md),
        SkeletonLoader(
          width: double.infinity,
          height: 6,
          radius: BorderRadius.all(Radius.circular(3)),
        ),
      ],
    );
  }
}
