import 'package:flutter/material.dart';
import 'package:lucide_flutter/lucide_flutter.dart';

import '../../../app/theme/tokens.dart';
import '../../../core/widgets/dashed_divider.dart';
import '../../../core/widgets/ghost_button.dart';
import '../../../core/widgets/label_caps.dart';

/// Themed confirmation for the destructive Delete action (05 §2.5): rust
/// confirm button, parchment surface, honest "cannot be undone" copy.
Future<bool?> confirmDeleteDialog(BuildContext context, int count) {
  return showDialog<bool>(
    context: context,
    builder: (BuildContext context) => AlertDialog(
      backgroundColor: AppColors.parchment100,
      title: Text('Delete $count ${count == 1 ? 'image' : 'images'}?'),
      content: const Text(
        'The rows and their files leave the studio for good. '
        'This cannot be undone.',
      ),
      actions: <Widget>[
        GhostButton(
          label: 'Cancel',
          onPressed: () => Navigator.of(context).pop(false),
        ),
        TextButton(
          style: TextButton.styleFrom(
            foregroundColor: AppColors.rust400,
          ),
          onPressed: () => Navigator.of(context).pop(true),
          child: const Text('Delete'),
        ),
      ],
    ),
  );
}

/// Floating multi-select bar (05 §2.5): count + Download zip / Delete /
/// Mark used, parked as the inner Scaffold's `bottomNavigationBar` so it
/// floats above the shell's tab bar. Actions disable (spinner) while one
/// is running; [offline] dims them with an explanatory caption until a
/// pull-to-refresh reconnects (05 §3) — the hosting screen keeps the
/// selection through marking — the workflow continues after flags flip
/// (web parity).
class SelectionToolbar extends StatelessWidget {
  const SelectionToolbar({
    super.key,
    required this.count,
    required this.busy,
    required this.offline,
    required this.onCancel,
    required this.onDownloadZip,
    required this.onDelete,
    required this.onMarkUsed,
  });

  final int count;
  final bool busy;

  /// The hosting screen knows the network is down (last failure was a
  /// NetworkException); action buttons dim + go inert, cancel stays live.
  final bool offline;
  final VoidCallback onCancel;
  final VoidCallback onDownloadZip;
  final VoidCallback onDelete;
  final VoidCallback onMarkUsed;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.parchment100,
      child: SafeArea(
        top: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Padding(
              padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.sm,
                vertical: AppSpacing.xs,
              ),
              child: Row(
                children: <Widget>[
                  IconButton(
                    onPressed: onCancel,
                    tooltip: 'Cancel selection',
                    icon: const Icon(LucideIcons.x, size: 20),
                  ),
                  LabelCaps(text: '$count selected'),
                  const SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: IgnorePointer(
                      ignoring: offline,
                      child: Opacity(
                        opacity: offline ? 0.5 : 1,
                        child: SingleChildScrollView(
                          scrollDirection: Axis.horizontal,
                          child: Row(
                            children: <Widget>[
                              GhostButton(
                                label: 'Download zip',
                                loading: busy,
                                onPressed: busy || offline
                                    ? () {}
                                    : onDownloadZip,
                              ),
                              const SizedBox(width: AppSpacing.xs),
                              GhostButton(
                                label: 'Delete',
                                loading: busy,
                                onPressed:
                                    busy || offline ? () {} : onDelete,
                              ),
                              const SizedBox(width: AppSpacing.xs),
                              GhostButton(
                                label: 'Mark used',
                                loading: busy,
                                onPressed:
                                    busy || offline ? () {} : onMarkUsed,
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
            if (offline)
              Padding(
                padding: const EdgeInsets.fromLTRB(
                  AppSpacing.lg,
                  0,
                  AppSpacing.lg,
                  AppSpacing.xs,
                ),
                child: Row(
                  children: <Widget>[
                    const Icon(
                      LucideIcons.wifiOff,
                      size: 14,
                      color: AppColors.rust400,
                    ),
                    const SizedBox(width: AppSpacing.xs),
                    Expanded(
                      child: Text(
                        'Offline — actions disabled. Pull to refresh.',
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                              color: AppColors.rust400,
                            ),
                      ),
                    ),
                  ],
                ),
              ),
            const DashedDivider(),
          ],
        ),
      ),
    );
  }
}
