import 'package:flutter/material.dart';

import '../../../app/theme/tokens.dart';
import '../../../core/utils/app_exception.dart';
import '../../../core/utils/ui_message.dart';
import '../../../core/widgets/empty_state.dart';
import '../../../core/widgets/error_view.dart';
import '../../../core/widgets/primary_button.dart';
import '../../../core/widgets/skeleton_loader.dart';
import '../domain/image_record.dart';
import 'record_card.dart';

/// Column count for the responsive gallery grid (05 §2.5):
/// 2 columns ≥360dp, 3 ≥600dp, 4 ≥900dp, 1 below.
int galleryColumnCount(double viewportWidth) {
  if (viewportWidth >= 900) {
    return 4;
  }
  if (viewportWidth >= 600) {
    return 3;
  }
  if (viewportWidth >= 360) {
    return 2;
  }
  return 1;
}

/// Responsive grid geometry for the current context. Assumes the screen
/// insets its scroll content by [AppSpacing.lg] on each side — cells come
/// out 1:1 (the image) plus a caption strip.
({int columns, double cellWidth}) galleryGridMetrics(BuildContext context) {
  final double viewport = MediaQuery.sizeOf(context).width;
  final int columns = galleryColumnCount(viewport);
  final double content = viewport - AppSpacing.lg * 2;
  return (
    columns: columns,
    cellWidth: (content - AppSpacing.md * (columns - 1)) / columns,
  );
}

/// Bottom padding allowance under each 1:1 image: caption gap + one line.
const double _captionAllowance = 24;

/// The loaded images as a grid sliver; long-press arms selection on a tile.
Widget galleryRecordsSliver({
  required ({int columns, double cellWidth}) metrics,
  required List<ImageRecord> items,
  required Set<String> selectedIds,
  required bool selectMode,
  required ValueChanged<ImageRecord> onTap,
  required ValueChanged<ImageRecord> onLongPress,
}) {
  return SliverPadding(
    // Top inset matches the sibling tabs' 16 dp content top.
    padding: const EdgeInsets.fromLTRB(
      AppSpacing.lg,
      AppSpacing.lg,
      AppSpacing.lg,
      AppSpacing.xl,
    ),
    sliver: SliverGrid(
      gridDelegate: _delegate(metrics),
      delegate: SliverChildBuilderDelegate(
        (BuildContext context, int index) {
          final ImageRecord record = items[index];
          return RecordCard(
            record: record,
            selected: selectedIds.contains(record.id),
            selectMode: selectMode,
            onTap: () => onTap(record),
            onLongPress: () => onLongPress(record),
          );
        },
        childCount: items.length,
      ),
    ),
  );
}

/// Initial-load skeleton: 12 tile placeholders (05 §2.5).
Widget gallerySkeletonSliver({
  required ({int columns, double cellWidth}) metrics,
  int tiles = 12,
}) {
  return SliverPadding(
    padding: const EdgeInsets.fromLTRB(
      AppSpacing.lg,
      AppSpacing.lg,
      AppSpacing.lg,
      AppSpacing.xl,
    ),
    sliver: SliverGrid(
      gridDelegate: _delegate(metrics),
      delegate: SliverChildBuilderDelegate(
        (BuildContext context, int index) => Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            SkeletonLoader(
              height: metrics.cellWidth,
              radius: const BorderRadius.all(Radius.circular(AppRadii.md)),
            ),
            const SizedBox(height: AppSpacing.xs),
            const SkeletonLoader(height: 12),
          ],
        ),
        childCount: tiles,
      ),
    ),
  );
}

/// "Loading more" footer: three tile skeletons under the grid (05 §2.5).
Widget galleryFooterSliver() {
  return SliverPadding(
    padding: const EdgeInsets.fromLTRB(
      AppSpacing.lg,
      0,
      AppSpacing.lg,
      AppSpacing.xl,
    ),
    sliver: SliverToBoxAdapter(
      child: Row(
        children: <Widget>[
          for (int i = 0; i < 3; i++) ...<Widget>[
            if (i > 0) const SizedBox(width: AppSpacing.md),
            const Expanded(
              child: AspectRatio(
                aspectRatio: 1,
                child: SkeletonLoader(
                  radius: BorderRadius.all(Radius.circular(AppRadii.md)),
                ),
              ),
            ),
          ],
        ],
      ),
    ),
  );
}

/// "Nothing matches this lens" (filtered) vs the no-batches-at-all state —
/// both copy strings come straight from 05 §2.5.
Widget galleryEmptyState({
  required bool lensFiltered,
  required VoidCallback onNewBatch,
}) {
  if (lensFiltered) {
    return const EmptyState(
      title: 'Nothing matches this lens',
      message: 'Loosen a filter or clear the folder scope to see more.',
    );
  }
  return EmptyState(
    title: 'The gallery is empty',
    message: 'Run the pipeline once and the gallery fills up here.',
    action: PrimaryButton(
      label: 'New batch',
      onPressed: onNewBatch,
    ),
  );
}

/// Inline failure above a stale grid (05 "error: inline at grid top, grid
/// keeps stale items"): retry refetches the current lens.
Widget galleryInlineError({
  required Object error,
  required VoidCallback onRetry,
}) {
  return Padding(
    padding: const EdgeInsets.fromLTRB(
      AppSpacing.lg,
      AppSpacing.sm,
      AppSpacing.lg,
      0,
    ),
    child: ErrorView(message: errorText(error), onRetry: onRetry),
  );
}

/// Human line for any thrown object (AppException → its story).
String errorText(Object error) =>
    error is AppException ? uiMessageFor(error) : 'Something went wrong.';

SliverGridDelegateWithFixedCrossAxisCount _delegate(
  ({int columns, double cellWidth}) metrics,
) {
  return SliverGridDelegateWithFixedCrossAxisCount(
    crossAxisCount: metrics.columns,
    mainAxisSpacing: AppSpacing.md,
    crossAxisSpacing: AppSpacing.md,
    mainAxisExtent: metrics.cellWidth + _captionAllowance,
  );
}
