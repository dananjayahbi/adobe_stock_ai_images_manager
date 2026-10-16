import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../app/theme/tokens.dart';
import '../../../app/theme/typography.dart';
import '../../../core/utils/app_exception.dart';
import '../../../core/utils/ui_message.dart';
import '../../../core/widgets/dashed_divider.dart';
import '../../../core/widgets/ghost_button.dart';
import '../../../core/widgets/label_caps.dart';
import '../../../core/widgets/primary_button.dart';
import '../../../core/widgets/toast_exception.dart';
import '../domain/delivery_item.dart';

/// Rows rendered in the sheet before the "… more rows" note kicks in —
/// keeping the first N is the 05 §2.8 contract (the export still carries
/// every row).
const int kCsvPreviewLineCap = 120;

/// Bottom sheet showing `POST /api/assets/csv/preview` text in the theme's
/// stamp (Special Elite) face, scrollable both ways, with the export action
/// parked at the bottom (05 §2.8: tap action → options sheet → run).
Future<void> showCsvPreviewSheet(
  BuildContext context, {
  required CsvPreview preview,
  required Future<String> Function() onExport,
}) {
  return showModalBottomSheet<void>(
    context: context,
    backgroundColor: AppColors.parchment100,
    isScrollControlled: true,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(12)),
    ),
    builder: (BuildContext context) => _CsvPreviewSheet(
      preview: preview,
      onExport: onExport,
    ),
  );
}

class _CsvPreviewSheet extends StatefulWidget {
  const _CsvPreviewSheet({
    required this.preview,
    required this.onExport,
  });

  final CsvPreview preview;
  final Future<String> Function() onExport;

  @override
  State<_CsvPreviewSheet> createState() => _CsvPreviewSheetState();
}

class _CsvPreviewSheetState extends State<_CsvPreviewSheet> {
  bool _busy = false;

  Future<void> _export() async {
    setState(() => _busy = true);
    try {
      final String path = await widget.onExport();
      if (!mounted) return;
      // Root-overlay toast — it survives the pop below.
      showAppToast(context, 'Saved to $path', tone: ToastTone.success);
      Navigator.of(context).pop();
    } catch (error) {
      if (!mounted) return;
      setState(() => _busy = false);
      showAppToast(context, _messageFor(error), tone: ToastTone.error);
    }
  }

  String _messageFor(Object error) =>
      error is AppException ? uiMessageFor(error) : 'Something went wrong.';

  @override
  Widget build(BuildContext context) {
    final CsvPreview preview = widget.preview;
    final List<String> lines = preview.lines;
    final List<String> shown =
        lines.length > kCsvPreviewLineCap
            ? lines.take(kCsvPreviewLineCap).toList()
            : lines;
    final double bottom = MediaQuery.paddingOf(context).bottom;

    return Padding(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.lg,
        AppSpacing.lg,
        AppSpacing.lg,
        AppSpacing.lg + bottom,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Expanded(child: LabelCaps(text: 'CSV PREVIEW')),
              IconButton(
                onPressed: () => Navigator.of(context).pop(),
                tooltip: 'Close preview',
                icon: const Icon(Icons.close, size: 20),
              ),
            ],
          ),
          Text(
            '${preview.rowCount} rows · ${preview.warnings.length} warnings · '
            '${preview.skipped.length} skipped',
            style: Theme.of(context).textTheme.labelMedium,
          ),
          if (preview.warnings.isNotEmpty) ...<Widget>[
            const SizedBox(height: AppSpacing.sm),
            for (final String warning in preview.warnings.take(3))
              Padding(
                padding: const EdgeInsets.only(bottom: AppSpacing.xs),
                child: Text(
                  warning,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: AppColors.rust400,
                      ),
                ),
              ),
          ],
          const SizedBox(height: AppSpacing.md),
          const DashedDivider(),
          const SizedBox(height: AppSpacing.md),
          Flexible(
            child: SingleChildScrollView(
              child: SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: Text(
                  shown.join('\n'),
                  softWrap: false,
                  style: buildStampStyle(
                    fontSize: 12,
                    color: AppColors.ink600,
                  ),
                ),
              ),
            ),
          ),
          if (lines.length > kCsvPreviewLineCap)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.sm),
              child: Text(
                '… ${lines.length - kCsvPreviewLineCap} more lines — the '
                'export still contains all ${preview.rowCount} rows.',
                style: Theme.of(context).textTheme.labelMedium,
              ),
            ),
          const SizedBox(height: AppSpacing.lg),
          Row(
            children: <Widget>[
              Expanded(
                child: GhostButton(
                  label: 'Close',
                  onPressed: _busy
                      ? null
                      : () => Navigator.of(context).pop(),
                ),
              ),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: PrimaryButton(
                  label: 'Export CSV',
                  loading: _busy,
                  onPressed: _busy ? null : _export,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

/// Destructive confirm for force-accept (05 §2.8 gestures: tap action →
/// options sheet → run): required reason field, rust confirm that stays
/// off until the reason is non-empty, haptic tick on commit only.
///
/// Returns the trimmed reason, or `null` on cancel — the caller then makes
/// **no** repository call. The dialog owns its [TextEditingController] and
/// disposes it with its own state, so the exit transition can rebuild
/// safely. Sits beside the preview sheet because the M4 file contract
/// keeps every delivery modal in this file.
Future<String?> showForceAcceptDialog(
  BuildContext context, {
  required int count,
}) async {
  final String? reason = await showDialog<String>(
    context: context,
    builder: (BuildContext context) => _ForceAcceptDialog(count: count),
  );
  if (reason == null || reason.isEmpty) return null;
  await HapticFeedback.mediumImpact();
  return reason;
}

class _ForceAcceptDialog extends StatefulWidget {
  const _ForceAcceptDialog({required this.count});

  final int count;

  @override
  State<_ForceAcceptDialog> createState() => _ForceAcceptDialogState();
}

class _ForceAcceptDialogState extends State<_ForceAcceptDialog> {
  final TextEditingController _reason = TextEditingController();

  @override
  void dispose() {
    _reason.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      backgroundColor: AppColors.parchment100,
      title: Text(
        'Force-accept ${widget.count} ${widget.count == 1 ? 'record' : 'records'}?',
      ),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            'The measured score stays honest — your reason is '
            'recorded alongside the override.',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          const SizedBox(height: AppSpacing.md),
          TextField(
            controller: _reason,
            autofocus: true,
            minLines: 2,
            maxLines: 4,
            decoration: const InputDecoration(
              hintText: 'Reason (required)',
            ),
            onChanged: (_) => setState(() {}),
          ),
        ],
      ),
      actions: <Widget>[
        GhostButton(
          label: 'Cancel',
          onPressed: () => Navigator.of(context).pop(null),
        ),
        TextButton(
          style: TextButton.styleFrom(
            foregroundColor: AppColors.rust400,
          ),
          onPressed: _reason.text.trim().isEmpty
              ? null
              : () => Navigator.of(context).pop(_reason.text.trim()),
          child: const Text('Force-accept'),
        ),
      ],
    );
  }
}
