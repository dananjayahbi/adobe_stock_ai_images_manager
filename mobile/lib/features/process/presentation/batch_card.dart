import 'package:flutter/material.dart';

import '../../../app/theme/tokens.dart';
import '../../../core/utils/formatters.dart';
import '../../../core/widgets/app_card.dart';
import '../../../core/widgets/dashed_divider.dart';
import '../../../core/widgets/label_caps.dart';
import '../../../core/widgets/progress_bar.dart';
import '../../../core/widgets/stamp_badge.dart';
import '../domain/batch.dart';

/// One row of the `/process` list (05 §2.7.1): name, media type, status
/// stamp, created date, step count and — while running — the progress bar.
///
/// Tap opens `/process/:batchId`; long-press is the row action (delete
/// confirm lives on the screen).
class BatchCard extends StatelessWidget {
  const BatchCard({
    super.key,
    required this.batch,
    required this.onTap,
    this.onLongPress,
  });

  /// The `BatchResponse` this row renders.
  final Batch batch;

  /// Opens the batch detail.
  final VoidCallback onTap;

  /// Row action menu (delete); null disables the gesture.
  final VoidCallback? onLongPress;

  /// draft → neutral, running → accent, completed → success, failed →
  /// failure, cancelled → neutral (05 §2.7.1 mapping).
  static StampTone toneFor(String status) => switch (status) {
        'running' => StampTone.accent,
        'completed' => StampTone.success,
        'failed' => StampTone.failure,
        _ => StampTone.neutral,
      };

  @override
  Widget build(BuildContext context) {
    final String status = batch.status;
    return Semantics(
      button: true,
      label: 'Batch ${batch.name}, $status',
      child: AppCard(
        child: InkWell(
          onTap: onTap,
          onLongPress: onLongPress,
          borderRadius: BorderRadius.circular(AppRadii.md),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Expanded(
                    child: Text(
                      batch.name,
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                  ),
                  StampBadge(label: status, tone: toneFor(status)),
                ],
              ),
              const SizedBox(height: AppSpacing.sm),
              Wrap(
                spacing: AppSpacing.sm,
                runSpacing: AppSpacing.xs,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: <Widget>[
                  LabelCaps(
                    text: batch.mediaType == 'png' ? 'Transparent' : 'Raster',
                  ),
                  LabelCaps(
                    text: '${batch.steps.length} steps',
                  ),
                  LabelCaps(text: '${batch.recordCount} images'),
                  if (batch.createdAt != null)
                    LabelCaps(text: formatDateTime(batch.createdAt!)),
                ],
              ),
              if (status == 'running') ...<Widget>[
                const SizedBox(height: AppSpacing.sm),
                ProgressBar(value: batch.progress),
              ],
              if (status == 'failed' && batch.error != null) ...<Widget>[
                const SizedBox(height: AppSpacing.sm),
                const DashedDivider(),
                Text(
                  batch.error!,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: AppColors.rust400,
                      ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
