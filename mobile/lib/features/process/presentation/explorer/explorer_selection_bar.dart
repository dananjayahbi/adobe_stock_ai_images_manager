import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../app/theme/tokens.dart';
import '../../../../core/widgets/primary_button.dart';
import '../../../../core/widgets/secondary_button.dart';
import '../../domain/batch_step.dart';
import '../batch_controller.dart';
import 'batch_config_sheet.dart';
import 'explorer_controller.dart';

/// Pinned bottom bar of `/process/pick`: `'N selected'` + `[Draft] [Run]`.
///
/// Both actions stay inert at zero selection. Draft saves without any
/// profile; Run needs one — the bar holds it back (and says why) when no
/// step profiles exist at all, while [BatchConfigSheet] re-checks per
/// media type before its confirm button unlocks.
class ExplorerSelectionBar extends ConsumerWidget {
  const ExplorerSelectionBar({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ExplorerState? state = ref.watch(explorerControllerProvider).value;
    final int count = state?.selected.length ?? 0;

    // Profiles exist per media type; the bar only needs "any at all" to
    // decide whether Run can even open the sheet.
    final AsyncValue<List<StepProfile>> raster = ref.watch(
      stepProfilesProvider('raster'),
    );
    final AsyncValue<List<StepProfile>> png = ref.watch(
      stepProfilesProvider('png'),
    );
    final bool profilesKnown = raster.hasValue && png.hasValue;
    final bool noProfiles =
        profilesKnown && raster.value!.isEmpty && png.value!.isEmpty;

    final Widget draftButton = _guard(
      enabled: count > 0,
      child: SecondaryButton(
        label: 'Draft',
        onPressed: () => _open(context, ref, BatchCreateMode.draft),
      ),
    );
    final Widget runButton = _guard(
      enabled: count > 0 && !noProfiles,
      child: PrimaryButton(
        label: 'Run',
        onPressed: () => _open(context, ref, BatchCreateMode.queue),
      ),
    );

    return Material(
      color: AppColors.leather,
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.lg,
            AppSpacing.md,
            AppSpacing.lg,
            AppSpacing.sm,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              if (noProfiles) ...<Widget>[
                Text(
                  'Step profile required to run — none yet.',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodySmall
                      ?.copyWith(color: AppColors.rust400),
                ),
                const SizedBox(height: AppSpacing.sm),
              ],
              Row(
                children: <Widget>[
                  Text(
                    '$count selected',
                    style: Theme.of(context).textTheme.titleSmall?.copyWith(
                      color: count > 0 ? AppColors.brass300 : AppColors.ink400,
                    ),
                  ),
                  const Spacer(),
                  draftButton,
                  const SizedBox(width: AppSpacing.md),
                  runButton,
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// Dim + inert wrapper (same treatment as the detail screen's offline
  /// guard) — the buttons keep their labels instead of swapping to a
  /// spinner when disabled.
  Widget _guard({required bool enabled, required Widget child}) => enabled
      ? child
      : Opacity(opacity: 0.5, child: IgnorePointer(child: child));

  Future<void> _open(
    BuildContext context,
    WidgetRef ref,
    BatchCreateMode mode,
  ) async {
    final ExplorerState? state = ref.read(explorerControllerProvider).value;
    if (state == null || state.selected.isEmpty) {
      return;
    }
    final List<String> files = state.selected.toList()..sort();
    final bool done = await showBatchConfigSheet(
      context,
      mode: mode,
      files: files,
    );
    if (!done || !context.mounted) {
      return;
    }
    ref.read(explorerControllerProvider.notifier).clearSelection();
    context.go('/process');
  }
}
