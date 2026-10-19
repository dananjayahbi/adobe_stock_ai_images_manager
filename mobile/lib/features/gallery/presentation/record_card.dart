import 'package:flutter/material.dart';
import 'package:lucide_flutter/lucide_flutter.dart';

import '../../../app/theme/tokens.dart';
import '../../../core/widgets/stamp_badge.dart';
import '../../../core/widgets/thumbnail.dart';
import '../domain/image_record.dart';
import 'image_state_presentation.dart';

/// One 1:1 gallery tile (05 §2.5): Hero'd thumbnail + state stamp in the
/// top-left corner + a single-line filename caption, with the selection
/// affordances layered on top in selection mode.
class RecordCard extends StatelessWidget {
  const RecordCard({
    super.key,
    required this.record,
    required this.selected,
    required this.selectMode,
    this.onTap,
    this.onLongPress,
  });

  final ImageRecord record;
  final bool selected;

  /// Multi-select mode is armed (checkboxes visible, taps toggle).
  final bool selectMode;
  final VoidCallback? onTap;
  final VoidCallback? onLongPress;

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;

    return Semantics(
      // Tile acts as the labeled image target for screen readers (04 §4:
      // semanticLabel = record title), mirroring the dashboard's tiles.
      button: true,
      label: record.generatedTitle ?? record.filename,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        onLongPress: onLongPress,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
          AspectRatio(
            aspectRatio: 1,
            child: Stack(
              fit: StackFit.expand,
              children: <Widget>[
                Hero(
                  tag: 'record-${record.id}',
                  child: Thumbnail(
                    path:
                        record.thumbnailPath ?? record.originalPath ?? record.filename,
                    radius: BorderRadius.circular(AppRadii.md),
                  ),
                ),
                Positioned(
                  top: AppSpacing.xs,
                  left: AppSpacing.xs,
                  child: StampBadge(
                    label: stateLabel(record.state),
                    tone: stateTone(record.state),
                  ),
                ),
                if (selectMode)
                  Positioned(
                    top: AppSpacing.xs,
                    right: AppSpacing.xs,
                    child: Container(
                      width: 22,
                      height: 22,
                      decoration: BoxDecoration(
                        color: selected
                            ? scheme.primary
                            : Colors.black.withValues(alpha: 0.35),
                        borderRadius: BorderRadius.circular(AppRadii.sm),
                        border: Border.all(color: Colors.white, width: 1.5),
                      ),
                      child: selected
                          ? const Icon(
                              LucideIcons.squareCheck,
                              size: 14,
                              color: Colors.white,
                            )
                          : const Icon(
                              LucideIcons.square,
                              size: 14,
                              color: Colors.white,
                            ),
                    ),
                  ),
                if (selected)
                  Positioned.fill(
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        border: Border.all(color: scheme.primary, width: 2.5),
                        borderRadius: BorderRadius.circular(AppRadii.md),
                      ),
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(height: AppSpacing.xs),
          Text(
            record.filename,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: Theme.of(context).textTheme.labelSmall?.copyWith(
                  color: AppColors.ink600,
                ),
          ),
        ],
      ),
      ),
    );
  }
}
