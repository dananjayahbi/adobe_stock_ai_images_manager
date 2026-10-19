import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:lucide_flutter/lucide_flutter.dart';

import '../../../app/lifecycle_observer.dart';
import '../../../app/theme/tokens.dart';
import '../../../core/utils/app_exception.dart';
import '../../../core/utils/formatters.dart';
import '../../../core/utils/ui_message.dart';
import '../../../core/widgets/app_card.dart';
import '../../../core/widgets/async_view.dart';
import '../../../core/widgets/dashed_divider.dart';
import '../../../core/widgets/empty_state.dart';
import '../../../core/widgets/error_view.dart';
import '../../../core/widgets/label_caps.dart';
import '../../../core/widgets/secondary_button.dart';
import '../../../core/widgets/skeleton_loader.dart';
import '../../../core/widgets/stamp_badge.dart';
import '../../../core/widgets/stamp_in.dart';
import '../../../core/widgets/status_chip.dart';
import '../../../core/widgets/toast_exception.dart';
import '../domain/delivery_item.dart';
import 'csv_preview_sheet.dart';
import 'delivery_controller.dart';
import 'delivery_widgets.dart';

/// `/delivery` (05 §2.8): deliverable-set summary with stage filter chips,
/// three action cards — CSV preview + export, ZIP bundle, force-accept —
/// selectable rows, and the session-local export history. Selection lives
/// on screen (the route contract carries no arguments). Backend wins over
/// 05 where they disagree: preview is a **POST**, the ZIP cap is 50, paths
/// go through `platformPath`. Offline = last contact was a network
/// failure: the note pins the cards off until a fetch succeeds again.
/// Sheets: `csv_preview_sheet.dart`; atoms: `delivery_widgets.dart`.
class DeliveryScreen extends ConsumerStatefulWidget {
  const DeliveryScreen({super.key});

  @override
  ConsumerState<DeliveryScreen> createState() => _DeliveryScreenState();
}

class _DeliveryScreenState extends ConsumerState<DeliveryScreen> {
  /// Last pull-to-refresh failure (05 §3): shown inline over the stale rows
  /// with a retry until the next successful pull clears it. Action failures
  /// keep using toasts — those are transient feedback.
  Object? _refreshError;

  @override
  Widget build(BuildContext context) {
    final AsyncValue<DeliveryState> async = ref.watch(deliveryControllerProvider);
    // Resume revalidation (03 §4): refresh this tab's controller when the
    // app returns to the foreground — container-based, outlives this element.
    final ProviderContainer container = ProviderScope.containerOf(context);
    AppLifecycleHooks.registerFeatureInvalidator(
      'delivery',
      () => container.invalidate(deliveryControllerProvider),
    );
    return Scaffold(
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _refresh,
          child: CustomScrollView(
            physics: const AlwaysScrollableScrollPhysics(),
            slivers: <Widget>[
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(AppSpacing.lg, AppSpacing.lg, AppSpacing.lg, AppSpacing.xxl),
                sliver: SliverToBoxAdapter(child: _content(context, ref, async)),
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// Title is local content: it stays put while AsyncView owns
  /// skeleton → data → inline error + retry (05 loading/error states).
  Widget _content(BuildContext context, WidgetRef ref, AsyncValue<DeliveryState> async) {
    final TextTheme theme = Theme.of(context).textTheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Text('Delivery', style: theme.displaySmall),
        const SizedBox(height: AppSpacing.sm),
        Text(
          'CSV metadata and ZIP bundles for Adobe — the rows and files '
          'always agree on the filename.',
          style: theme.bodySmall,
        ),
        const SizedBox(height: AppSpacing.xl),
        AsyncView<DeliveryState>(
          data: async,
          loading: _skeleton(),
          error: ErrorView(message: _messageFor(async.error), onRetry: () => ref.invalidate(deliveryControllerProvider)),
          builder: (DeliveryState state) => _body(context, ref, state),
        ),
      ],
    );
  }

  /// 05 loading state: three action-card skeletons (never a bare spinner).
  Widget _skeleton() => Column(
        children: <Widget>[
          SkeletonLoader.card(),
          const SizedBox(height: AppSpacing.md),
          SkeletonLoader.card(),
          const SizedBox(height: AppSpacing.md),
          SkeletonLoader.card(),
        ],
      );

  Widget _body(BuildContext context, WidgetRef ref, DeliveryState state) {
    if (state.isEmpty) {
      return EmptyState(
        title: 'Nothing to deliver yet',
        message: 'Once metadata is generated, its rows and files show up '
            'here ready for export.',
        action: SecondaryButton(
          label: 'Open gallery',
          onPressed: () => context.go('/gallery'),
        ),
      );
    }
    final DeliveryController controller = ref.read(deliveryControllerProvider.notifier);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        if (state.offline) ...<Widget>[
          _offlineNote(context),
          const SizedBox(height: AppSpacing.md),
        ],
        if (_refreshError != null && !state.offline) ...<Widget>[
          ErrorView(message: _messageFor(_refreshError), onRetry: _refresh),
          const SizedBox(height: AppSpacing.md),
        ],
        _summary(context, state, controller),
        const SizedBox(height: AppSpacing.lg),
        _actionCards(context, ref, state),
        const SizedBox(height: AppSpacing.xl),
        _rows(context, state, controller),
        if (state.exports.isNotEmpty) ...<Widget>[
          const SizedBox(height: AppSpacing.xl),
          _history(context, state),
        ],
      ],
    );
  }

  Widget _offlineNote(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: AppSpacing.sm),
        decoration: BoxDecoration(
          color: AppColors.rust400.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(AppRadii.sm),
        ),
        child: Row(children: <Widget>[
          const Icon(LucideIcons.triangleAlert, size: 16),
          const SizedBox(width: AppSpacing.sm),
          Expanded(child: Text('Offline — actions disabled. Pull to refresh.', style: Theme.of(context).textTheme.bodySmall)),
        ]),
      );

  Widget _summary(BuildContext context, DeliveryState state, DeliveryController controller) {
    final TextTheme theme = Theme.of(context).textTheme;
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const LabelCaps(text: 'DELIVERABLE SET'),
          const SizedBox(height: AppSpacing.sm),
          Text('${formatCount(state.deliverableCount)} rows ready for Adobe', style: theme.titleMedium?.copyWith(fontWeight: FontWeight.w600)),
          Text('${formatCount(state.candidates.length)} records · ${formatCount(state.selectedCount)} selected', style: theme.bodySmall),
          const SizedBox(height: AppSpacing.md),
          Wrap(spacing: AppSpacing.sm, runSpacing: AppSpacing.xs, children: <Widget>[
              for (final DeliveryFilter filter in DeliveryFilter.values)
                StatusChip(label: filter.label, icon: _filterIcon(filter), tone: state.filter == filter ? StatusTone.accent : StatusTone.neutral, onTap: () => controller.setFilter(filter)),
            ],
          ),
        ],
      ),
    );
  }

  IconData _filterIcon(DeliveryFilter filter) => switch (filter) {
        DeliveryFilter.all => LucideIcons.listChecks,
        DeliveryFilter.deliverable => LucideIcons.circleCheck,
        DeliveryFilter.forceable => LucideIcons.gavel,
      };

  Widget _actionCards(BuildContext context, WidgetRef ref, DeliveryState state) {
    final bool enabled = !state.offline;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        ActionCard(
          icon: LucideIcons.fileSpreadsheet,
          title: 'CSV preview & export',
          caption: 'Review the Adobe CSV, then save it to downloads.',
          busy: state.busy == DeliveryAction.preview || state.busy == DeliveryAction.csv,
          enabled: enabled,
          onTap: () => _previewAndExport(context, ref),
        ),
        const SizedBox(height: AppSpacing.md),
        ActionCard(
          icon: LucideIcons.archive,
          title: 'ZIP bundle',
          caption: state.selection.isEmpty
              ? 'Select rows below — up to ${DeliveryController.maxBundleFiles} '
                  'files with their matching CSV.'
              : '${formatCount(state.selectedCount)} selected · images + '
                  'matching CSV (max ${DeliveryController.maxBundleFiles}).',
          busy: state.busy == DeliveryAction.zip,
          enabled: enabled,
          onTap: () => _bundle(context, ref),
        ),
        const SizedBox(height: AppSpacing.md),
        ActionCard(
          icon: LucideIcons.gavel,
          title: 'Force-accept',
          caption: 'Override the acceptance gate for the selection — a '
              'reason is required.',
          busy: state.busy == DeliveryAction.force,
          enabled: enabled,
          onTap: () => _confirmForceAccept(context, ref, state),
        ),
      ],
    );
  }

  void _toast(BuildContext context, String message, ToastTone tone) =>
      showAppToast(context, message, tone: tone);

  Future<void> _refresh() async {
    try {
      await ref.read(deliveryControllerProvider.notifier).refresh();
      if (mounted) setState(() => _refreshError = null);
    } catch (error) {
      if (mounted) setState(() => _refreshError = error);
    }
  }

  Future<void> _previewAndExport(BuildContext context, WidgetRef ref) async {
    final DeliveryController controller = ref.read(deliveryControllerProvider.notifier);
    try {
      final CsvPreview preview = await controller.previewForAction();
      if (!context.mounted) return;
      await showCsvPreviewSheet(
        context,
        preview: preview,
        onExport: () => controller.exportCsv(),
      );
    } catch (error) {
      if (context.mounted) _toast(context, _messageFor(error), ToastTone.error);
    }
  }

  Future<void> _bundle(BuildContext context, WidgetRef ref) async {
    try {
      final String path = await ref.read(deliveryControllerProvider.notifier).bundleZip();
      if (context.mounted) _toast(context, 'Saved to $path', ToastTone.success);
    } catch (error) {
      if (context.mounted) _toast(context, _messageFor(error), ToastTone.error);
    }
  }

  /// Cancel returns null → the repository is never touched. Haptic on
  /// confirm only (05 destructive confirms).
  Future<void> _confirmForceAccept(BuildContext context, WidgetRef ref, DeliveryState state) async {
    final DeliveryController controller = ref.read(deliveryControllerProvider.notifier);
    final String? reason = await showForceAcceptDialog(context, count: state.selectedCount);
    if (reason == null || !context.mounted) return;
    try {
      final ForceAcceptOutcome outcome = await controller.forceAccept(reason);
      if (context.mounted) {
        _toast(
          context,
          'Force-accepted ${formatCount(outcome.accepted)} · refused '
          '${formatCount(outcome.refused)}',
          ToastTone.success,
        );
      }
    } catch (error) {
      if (context.mounted) _toast(context, _messageFor(error), ToastTone.error);
    }
  }

  Widget _rows(BuildContext context, DeliveryState state, DeliveryController controller) {
    final List<DeliveryCandidate> rows = state.visibleCandidates;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Row(children: <Widget>[
          const Expanded(child: LabelCaps(text: 'DELIVERY ROWS')),
          Text('${formatCount(rows.length)} shown', style: Theme.of(context).textTheme.labelMedium),
        ]),
        const SizedBox(height: AppSpacing.sm),
        AppCard(
          padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
          child: Column(
            children: <Widget>[
              for (int i = 0; i < rows.length; i++) ...<Widget>[
                if (i > 0) const DashedDivider(),
                _rowTile(context, rows[i], state, controller),
              ],
            ],
          ),
        ),
      ],
    );
  }

  /// Plain InkWell row (ListTile asserts against AppCard's decorated
  /// background); checkbox + delivery name + stage chip, dimmed offline.
  Widget _rowTile(BuildContext context, DeliveryCandidate candidate, DeliveryState state, DeliveryController controller) {
    final TextTheme theme = Theme.of(context).textTheme;
    final bool selected = state.selection.contains(candidate.id);
    final bool disabled = state.offline;
    final String? title = candidate.title == candidate.effectiveName ? null : candidate.title;
    return InkWell(
      onTap: disabled ? null : () => controller.toggleRecord(candidate.id),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xs, vertical: AppSpacing.xs),
        child: Row(
          children: <Widget>[
            Checkbox(
              value: selected,
              activeColor: AppColors.brass400,
              onChanged: disabled ? null : (_) => controller.toggleRecord(candidate.id),
            ),
            const SizedBox(width: AppSpacing.xs),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(candidate.effectiveName, maxLines: 1, overflow: TextOverflow.ellipsis, style: theme.titleSmall),
                  if (title != null)
                    Text(title, maxLines: 1, overflow: TextOverflow.ellipsis, style: theme.labelMedium),
                ],
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            StatusChip(
              label: candidate.stage,
              icon: stageIcon(candidate.stage),
              tone: stageTone(candidate.stage),
            ),
          ],
        ),
      ),
    );
  }

  Widget _history(BuildContext context, DeliveryState state) => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          const LabelCaps(text: 'RECENT EXPORTS'),
          const SizedBox(height: AppSpacing.sm),
          AppCard(
            child: Column(
              children: <Widget>[
                for (int i = 0; i < state.exports.length; i++) ...<Widget>[
                  if (i > 0) const DashedDivider(),
                  _exportRow(context, state.exports[i]),
                ],
              ],
            ),
          ),
        ],
      );

  Widget _exportRow(BuildContext context, ExportRecord record) {
    final TextTheme theme = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
      child: Row(
        children: <Widget>[
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(record.fileName, style: theme.titleSmall),
                Text('${record.kind.label} · ${formatBytes(record.byteCount)} · ${formatDateTime(record.exportedAt)}', style: theme.labelMedium),
              ],
            ),
          ),
          StampIn(child: StampBadge(label: 'EXPORTED', tone: StampTone.success)),
        ],
      ),
    );
  }
}
String _messageFor(Object? error) =>
    error is AppException ? uiMessageFor(error) : 'Something went wrong.';
