import 'package:flutter/material.dart';
import 'package:lucide_flutter/lucide_flutter.dart';

import '../../../app/theme/tokens.dart';
import '../../../core/widgets/app_card.dart';
import '../../../core/widgets/dashed_divider.dart';
import '../../../core/widgets/label_caps.dart';
import '../../../core/widgets/live_dot.dart';
import '../../../core/widgets/progress_bar.dart';
import '../../../core/widgets/stamp_badge.dart';
import '../../../core/widgets/status_chip.dart';
import '../domain/batch_step.dart';

/// Vertical stepper over `batch.steps[]` (05 §2.7.2), fed by live batch
/// snapshots: one [AppCard] per step — index stamp, label, config summary
/// chips, per-step status + per-image results — [DashedDivider] between.
/// The running step also carries a [LiveDot] and a per-step [ProgressBar].
class StepTimeline extends StatelessWidget {
  const StepTimeline({
    super.key,
    required this.steps,
    required this.progress,
    this.catalog,
  });

  /// Ordered `[{key, config}]` from the batch payload.
  final List<BatchStep> steps;

  /// `step_progress` map from the newest snapshot (null before a run).
  final Map<String, StepProgress>? progress;

  /// Step catalog — supplies human labels/descriptions; keys render
  /// as-is while it loads (or if the catalog fetch failed).
  final StepCatalog? catalog;

  @override
  Widget build(BuildContext context) {
    if (steps.isEmpty) {
      return const SizedBox.shrink();
    }
    final List<Widget> children = <Widget>[];
    for (int index = 0; index < steps.length; index++) {
      final BatchStep step = steps[index];
      children.add(
        _StepCard(
          position: index + 1,
          step: step,
          state: progress?[step.key],
          label: catalog?.labelFor(step.key) ?? step.key,
          description: catalog?.descriptionFor(step.key),
        ),
      );
      if (index != steps.length - 1) {
        children.add(const DashedDivider());
      }
    }
    return Column(children: children);
  }
}

class _StepCard extends StatelessWidget {
  const _StepCard({
    required this.position,
    required this.step,
    required this.state,
    required this.label,
    this.description,
  });

  /// 1-based position shown in the index stamp.
  final int position;

  final BatchStep step;

  /// This step's live progress, if the batch has reported one.
  final StepProgress? state;

  final String label;

  final String? description;

  @override
  Widget build(BuildContext context) {
    final String status = state?.status ?? 'pending';
    final _StatusVisual visual = _visualFor(status);
    final String? message = state?.message;
    final Map<String, int>? counts = state?.counts;
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              StampBadge(label: '$position', tone: StampTone.neutral),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(label, style: Theme.of(context).textTheme.titleSmall),
                    if (description != null && description!.isNotEmpty)
                      Text(
                        description!,
                        style: Theme.of(context).textTheme.bodySmall
                            ?.copyWith(color: AppColors.ink400),
                      ),
                  ],
                ),
              ),
              if (status == 'running') ...<Widget>[
                const LiveDot(label: 'RUN'),
                const SizedBox(width: AppSpacing.sm),
              ],
              StatusChip(label: status, icon: visual.icon, tone: visual.tone),
            ],
          ),
          if (message != null && message.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            Text(
              message,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: visual.tone == StatusTone.failure
                        ? AppColors.rust400
                        : AppColors.ink200,
                  ),
            ),
          ] else if (counts != null && counts.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            Text(_countsLine(counts), style: Theme.of(context).textTheme.bodySmall),
          ],
          if (status == 'running') ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            ProgressBar(value: _fraction(counts), height: 4),
          ],
          const SizedBox(height: AppSpacing.sm),
          _configRow(context),
        ],
      ),
    );
  }

  /// Config summary chips — MVP ships defaults-only (per-step config
  /// editing is deferred; 05 §2.7.2 config sheet comes later).
  Widget _configRow(BuildContext context) {
    if (step.config.isEmpty) {
      return const LabelCaps(text: 'defaults');
    }
    return Wrap(
      spacing: AppSpacing.xs,
      runSpacing: AppSpacing.xs,
      children: <Widget>[
        for (final MapEntry<String, Object?> entry in step.config.entries)
          _ConfigChip(text: '${entry.key}: ${entry.value}'),
      ],
    );
  }

  static String _countsLine(Map<String, int> counts) {
    final int ok = counts['succeeded'] ?? 0;
    final int failed = counts['failed'] ?? 0;
    final int skipped = counts['skipped'] ?? 0;
    return '$ok ok · $failed failed · $skipped skipped';
  }

  /// Processed fraction of one running step (same math as `Batch.progress`).
  static double? _fraction(Map<String, int>? counts) {
    if (counts == null || counts.isEmpty) {
      return null;
    }
    int total = 0;
    for (final int value in counts.values) {
      total += value;
    }
    if (total == 0) {
      return null;
    }
    final int pending = (counts['pending'] ?? 0) + (counts['running'] ?? 0);
    return ((total - pending) / total).clamp(0.0, 1.0);
  }

  static _StatusVisual _visualFor(String status) => switch (status) {
        'completed' =>
          const _StatusVisual(LucideIcons.circleCheck, StatusTone.success),
        'failed' => const _StatusVisual(LucideIcons.circleX, StatusTone.failure),
        'running' =>
          const _StatusVisual(LucideIcons.loaderCircle, StatusTone.accent),
        'cancelled' => const _StatusVisual(LucideIcons.ban, StatusTone.neutral),
        _ => const _StatusVisual(LucideIcons.circleDashed, StatusTone.neutral),
      };
}

class _StatusVisual {
  const _StatusVisual(this.icon, this.tone);

  final IconData icon;
  final StatusTone tone;
}

class _ConfigChip extends StatelessWidget {
  const _ConfigChip({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.sm,
          vertical: AppSpacing.xs,
        ),
        decoration: BoxDecoration(
          color: AppColors.parchment300,
          borderRadius: BorderRadius.circular(AppRadii.sm),
        ),
        child: Text(
          text,
          style: Theme.of(context)
              .textTheme
              .labelSmall
              ?.copyWith(color: AppColors.ink200),
        ),
      );
}
