import 'package:flutter/material.dart';

import '../../../app/theme/tokens.dart';
import '../../../core/utils/app_exception.dart';
import '../../../core/utils/formatters.dart';
import '../../../core/utils/ui_message.dart';
import '../../../core/widgets/app_card.dart';
import '../../../core/widgets/dashed_divider.dart';
import '../../../core/widgets/error_view.dart';
import '../../../core/widgets/label_caps.dart';
import '../../../core/widgets/skeleton_loader.dart';
import '../../../core/widgets/stamp_badge.dart';
import '../../../core/widgets/status_chip.dart';
import '../domain/image_record.dart';
import 'image_state_presentation.dart';
import 'keyword_chips.dart';

/// Bottom draggable metadata sheet: two snaps (~28% / 75%) holding the
/// postmark metadata card (05 §2.6).
///
/// The [footer] slot pins the review action bar at the sheet's bottom edge,
/// so Approve stays thumb-reachable at either snap while the card scrolls
/// above it. Loading, record-error and data states are folded into the
/// scroll content — the sheet chrome never disappears.
class MetadataSheet extends StatelessWidget {
  const MetadataSheet({
    super.key,
    required this.record,
    required this.loading,
    this.controller,
    this.error,
    this.onRetry,
    this.footer,
  });

  /// Current record; null while the first fetch is in flight.
  final ImageRecord? record;

  /// True while the initial fetchById runs (skeleton rows).
  final bool loading;

  /// Sheet position controller owned by the detail screen — lets it inset
  /// the media viewport by the sheet's live extent (R5 drawer clearance).
  final DraggableScrollableController? controller;

  /// Failed fetchById; rendered as an inline ErrorView inside the sheet.
  final Object? error;

  /// Retry hook for the sheet error state.
  final VoidCallback? onRetry;

  /// Pinned below the scrollable — the ReviewActionBar.
  final Widget? footer;

  @override
  Widget build(BuildContext context) {
    return DraggableScrollableSheet(
      controller: controller,
      initialChildSize: 0.28,
      minChildSize: 0.28,
      maxChildSize: 0.75,
      snap: true,
      builder: (BuildContext context, ScrollController scrollController) {
        return DecoratedBox(
          decoration: const BoxDecoration(
            color: AppColors.parchment50,
            border: Border(top: BorderSide(color: AppColors.parchment400)),
            borderRadius: BorderRadius.vertical(
              top: Radius.circular(AppRadii.md),
            ),
          ),
          child: Column(
            children: <Widget>[
              Expanded(
                child: ListView(
                  controller: scrollController,
                  physics: const AlwaysScrollableScrollPhysics(),
                  padding: const EdgeInsets.fromLTRB(
                    AppSpacing.lg,
                    AppSpacing.sm,
                    AppSpacing.lg,
                    AppSpacing.lg,
                  ),
                  children: <Widget>[
                    Center(
                      child: Container(
                        width: 40,
                        height: 4,
                        decoration: const BoxDecoration(
                          color: AppColors.parchment500,
                          borderRadius: BorderRadius.all(
                            Radius.circular(AppRadii.sm),
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(height: AppSpacing.md),
                    _sheetBody(),
                  ],
                ),
              ),
              ?footer,
            ],
          ),
        );
      },
    );
  }

  /// Error / skeleton / data switch for the scroll content.
  Widget _sheetBody() {
    final Object? fetchError = error;
    if (fetchError != null) {
      return ErrorView(
        message: fetchError is AppException
            ? uiMessageFor(fetchError)
            : 'Something went wrong.',
        onRetry: onRetry,
      );
    }
    final ImageRecord? current = record;
    if (loading || current == null) {
      return const _SheetSkeleton();
    }
    return _MetadataCard(record: current);
  }
}

/// Skeleton stand-in while `GET /api/records/{id}` resolves.
class _SheetSkeleton extends StatelessWidget {
  const _SheetSkeleton();

  @override
  Widget build(BuildContext context) {
    return const Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        SkeletonLoader(height: 20, width: 180),
        SizedBox(height: AppSpacing.md),
        SkeletonLoader(height: 14),
        SizedBox(height: AppSpacing.sm),
        SkeletonLoader(height: 14),
        SizedBox(height: AppSpacing.sm),
        SkeletonLoader(height: 14),
      ],
    );
  }
}

/// The postmark metadata card: filename stamp, title/description preview,
/// keyword chips, acceptance facts (05 §2.6, web InfoPanel parity).
class _MetadataCard extends StatelessWidget {
  const _MetadataCard({required this.record});

  final ImageRecord record;

  @override
  Widget build(BuildContext context) {
    final TextTheme textTheme = Theme.of(context).textTheme;
    final String title =
        (record.generatedTitle?.isNotEmpty ?? false)
            ? record.generatedTitle!
            : record.filename;

    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Expanded(
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: FittedBox(
                    fit: BoxFit.scaleDown,
                    child: StampBadge(label: record.filename, tone: StampTone.neutral),
                  ),
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              StampBadge(
                label: stateLabel(record.state),
                tone: stateTone(record.state),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.md),
          Text(
            title,
            style: textTheme.titleMedium?.copyWith(color: AppColors.ink800),
          ),
          if (record.generatedDescription?.isNotEmpty ?? false) ...<Widget>[
            const SizedBox(height: AppSpacing.md),
            const DashedDivider(),
            const SizedBox(height: AppSpacing.md),
            const LabelCaps(text: 'Description'),
            const SizedBox(height: AppSpacing.sm),
            Text(
              record.generatedDescription!,
              maxLines: 4,
              overflow: TextOverflow.ellipsis,
              style: textTheme.bodyMedium?.copyWith(
                color: AppColors.ink600,
                height: 1.45,
              ),
            ),
          ],
          if (record.generatedKeywords?.isNotEmpty ?? false) ...<Widget>[
            const SizedBox(height: AppSpacing.md),
            const DashedDivider(),
            const SizedBox(height: AppSpacing.md),
            const LabelCaps(text: 'Keywords'),
            const SizedBox(height: AppSpacing.xs),
            // Dense brass hairline pills, content-sized so several share
            // each run — every keyword visible, none stacked full-width.
            KeywordChips(keywords: record.generatedKeywords!),
          ],
          if (record.flags.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.md),
            const DashedDivider(),
            const SizedBox(height: AppSpacing.md),
            const LabelCaps(text: 'Flags'),
            const SizedBox(height: AppSpacing.sm),
            Wrap(
              spacing: AppSpacing.sm,
              runSpacing: AppSpacing.sm,
              children: record.flags
                  .map(
                    (String flag) => StatusChip(
                      label: flagLabel(flag),
                      icon: flagIcon(flag),
                      tone: flagChipTone(flag),
                    ),
                  )
                  .toList(growable: false),
            ),
          ],
          if (_facts.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.md),
            const DashedDivider(),
            const SizedBox(height: AppSpacing.md),
            const LabelCaps(text: 'Details'),
            const SizedBox(height: AppSpacing.sm),
            ..._facts.map(
              (Widget row) => Padding(
                padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
                child: row,
              ),
            ),
          ],
        ],
      ),
    );
  }

  /// Acceptance / dimensions / size / category / stage rows — only the
  /// facts the record actually has (web InfoPanel parity).
  List<Widget> get _facts {
    final List<Widget> rows = <Widget>[];
    final double? score = record.acceptanceScore;
    if (score != null) {
      rows.add(
        _FactRow(label: 'Acceptance', value: '${(score * 100).round()}%'),
      );
    }
    final int? width = record.width;
    final int? height = record.height;
    if (width != null && height != null) {
      rows.add(_FactRow(label: 'Dimensions', value: '$width × $height px'));
    }
    final int? bytes = record.fileSizeBytes;
    if (bytes != null) {
      rows.add(_FactRow(label: 'File size', value: formatBytes(bytes)));
    }
    final int? category = record.category;
    if (category != null) {
      rows.add(
        _FactRow(label: 'Category', value: 'Adobe category $category'),
      );
    }
    final String? stage = record.stage;
    if (stage != null && stage.isNotEmpty) {
      rows.add(_FactRow(label: 'Stage', value: stage));
    }
    return rows;
  }
}

/// Label/value line inside the metadata card's Details section.
class _FactRow extends StatelessWidget {
  const _FactRow({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final TextTheme textTheme = Theme.of(context).textTheme;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        SizedBox(width: 96, child: LabelCaps(text: label)),
        Expanded(
          child: Text(
            value,
            textAlign: TextAlign.right,
            style: textTheme.bodySmall?.copyWith(
              color: AppColors.ink600,
              height: 1.4,
            ),
          ),
        ),
      ],
    );
  }
}
