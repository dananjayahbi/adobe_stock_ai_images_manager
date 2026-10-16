import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:lucide_flutter/lucide_flutter.dart';

import '../../platforms/presentation/platforms_controller.dart';
import '../../../app/lifecycle_observer.dart';
import '../../../app/theme/tokens.dart';
import '../../../core/utils/app_exception.dart';
import '../../../core/utils/ui_message.dart';
import '../../../core/widgets/app_card.dart';
import '../../../core/widgets/async_view.dart';
import '../../../core/widgets/connection_profile_banner.dart';
import '../../../core/widgets/empty_state.dart';
import '../../../core/widgets/error_view.dart';
import '../../../core/widgets/label_caps.dart';
import '../../../core/widgets/live_dot.dart';
import '../../../core/widgets/primary_button.dart';
import '../../../core/widgets/progress_bar.dart';
import '../../../core/widgets/secondary_button.dart';
import '../../../core/widgets/status_chip.dart';
import '../../../core/widgets/thumbnail.dart';
import '../../../core/widgets/toast_exception.dart';
import '../domain/dashboard_stats.dart';
import 'dashboard_controller.dart';
import 'stat_tile.dart';

/// `/home` — Adobe Dashboard (05 §2.4), parity with web `/adobe-stock`:
/// connection banner + hero, 2×2 stats, Latest grid, running-job card.
///
/// Each data section renders from its own [SectionState]: loading shows a
/// per-card skeleton, failure an inline [ErrorView] with retry, and the
/// hero/shell never depend on the network — one endpoint down must not kill
/// the page. Pull-to-refresh reloads all four sections.
class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final String platformId = ref.watch(activePlatformIdProvider);
    final AsyncValue<DashboardStats> stats = ref.watch(dashboardControllerProvider(platformId));
    // Resume revalidation (03 §4): refresh this tab's controllers when the
    // app returns to the foreground — container-based, so the stored hook
    // outlives this element.
    final ProviderContainer container = ProviderScope.containerOf(context);
    AppLifecycleHooks.registerFeatureInvalidator(
      'dashboard',
      () => container.invalidate(dashboardControllerProvider),
    );
    return Scaffold(
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: () => ref.read(dashboardControllerProvider(platformId).notifier).refreshAll(),
          child: CustomScrollView(
            physics: const AlwaysScrollableScrollPhysics(),
            slivers: <Widget>[
              const SliverToBoxAdapter(child: ConnectionProfileBanner()),
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(AppSpacing.lg, AppSpacing.lg, AppSpacing.lg, AppSpacing.xxl),
                sliver: SliverToBoxAdapter(
                  child: AsyncView<DashboardStats>(
                    data: stats,
                    loading: _body(context, ref, platformId, const DashboardStats.loading()),
                    onRetry: () => ref.invalidate(dashboardControllerProvider(platformId)),
                    builder: (DashboardStats value) => _body(context, ref, platformId, value),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _body(BuildContext context, WidgetRef ref, String platformId, DashboardStats stats) {
    final DashboardController controller = ref.read(dashboardControllerProvider(platformId).notifier);
    final JobSummary? activeJob = stats.activeJob;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        _hero(context),
        const SizedBox(height: AppSpacing.xl),
        _statsGrid(stats, controller),
        const SizedBox(height: AppSpacing.xl),
        _latestSection(context, stats, controller),
        if (stats.jobs case SectionLoading<List<JobSummary>>()) ...<Widget>[
          const SizedBox(height: AppSpacing.xl),
          const AppCard(child: RunningJobSkeleton()),
        ] else if (stats.jobs case SectionError<List<JobSummary>>(:final error)) ...<Widget>[
          const SizedBox(height: AppSpacing.xl),
          ErrorView(
            message: _messageFor(error),
            onRetry: () => controller.retrySection(DashboardSection.jobs),
          ),
        ] else if (activeJob != null) ...<Widget>[
          const SizedBox(height: AppSpacing.xl),
          _runningJobCard(context, activeJob),
        ],
      ],
    );
  }

  // --------------------------------------------------------------- hero ---

  Widget _hero(BuildContext context) {
    final TextTheme textTheme = Theme.of(context).textTheme;
    return AppCard(
      padding: const EdgeInsets.all(AppSpacing.xl),
      child: Column(
        children: <Widget>[
          const LabelCaps(text: 'A local pipeline for Adobe Stock'),
          const SizedBox(height: AppSpacing.md),
          Text.rich(
            TextSpan(children: <InlineSpan>[
              TextSpan(text: 'Process images in ', style: textTheme.displaySmall),
              TextSpan(
                text: 'batches',
                style: GoogleFonts.ebGaramond(
                  fontSize: 36,
                  height: 1.2,
                  fontWeight: FontWeight.w600,
                  fontStyle: FontStyle.italic,
                  color: AppColors.oxblood400,
                ),
              ),
            ]),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: AppSpacing.md),
          Text(
            'Choose raster photos or transparent cut-outs, pick exactly the '
            'steps you need, and run the whole pipeline in one go.',
            textAlign: TextAlign.center,
            style: textTheme.bodyMedium?.copyWith(color: AppColors.ink600, height: 1.5),
          ),
          const SizedBox(height: AppSpacing.lg),
          Wrap(
            alignment: WrapAlignment.center,
            spacing: AppSpacing.md,
            runSpacing: AppSpacing.sm,
            children: <Widget>[
              PrimaryButton(
                label: 'New batch',
                onPressed: () => showAppToast(context, 'Batch wizard arrives with M4'),
              ),
              SecondaryButton(
                label: 'Open gallery',
                onPressed: () => context.go('/gallery'),
              ),
            ],
          ),
        ],
      ),
    );
  }

  // -------------------------------------------------------------- stats ---

  /// 2×2 grid of stat tiles. `IntrinsicHeight` + stretched rows keep an
  /// inline error cell from clipping while peers fill the same row height.
  Widget _statsGrid(DashboardStats stats, DashboardController controller) {
    final List<Widget> cells = <Widget>[
      _statCell<StagesSummary>(
        stats.stages,
        controller,
        section: DashboardSection.stages,
        data: (StagesSummary s) => StatTile(
          value: '${s.total}',
          label: 'Records total',
          tone: StatusTone.accent,
        ),
      ),
      _statCell<StagesSummary>(
        stats.stages,
        controller,
        section: DashboardSection.stages,
        data: (StagesSummary s) => StatTile(
          value: '${s.ready}',
          label: 'Ready to publish',
          tone: StatusTone.success,
        ),
      ),
      _statCell<QueuesSummary>(
        stats.queues,
        controller,
        section: DashboardSection.queues,
        data: (QueuesSummary q) => StatTile(
          value: '${q.total}',
          label: 'Queue depth',
          tone: StatusTone.neutral,
        ),
      ),
      _statCell<List<JobSummary>>(
        stats.jobs,
        controller,
        section: DashboardSection.jobs,
        data: _runningTile,
      ),
    ];
    // Per-row IntrinsicHeight: each Row must receive a *bounded* height so
    // crossAxisAlignment.stretch can fill cells (a Column hands its children
    // loose 0..∞ heights, which stretch would turn into tight-∞ and crash).
    return Column(
      children: <Widget>[
        IntrinsicHeight(child: _gridRow(cells[0], cells[1])),
        const SizedBox(height: AppSpacing.md),
        IntrinsicHeight(child: _gridRow(cells[2], cells[3])),
      ],
    );
  }

  /// Equal-width stat cells. `spacing` (not a gap widget) keeps every child
  /// flexible — a non-flex child would make the Row's cross-intrinsic height
  /// unbounded under IntrinsicHeight.
  Widget _gridRow(Widget a, Widget b) => Row(
        spacing: AppSpacing.md,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[Expanded(child: a), Expanded(child: b)],
      );

  /// One cell folded from its section state: skeleton / inline error / tile.
  Widget _statCell<T>(
    SectionState<T> state,
    DashboardController controller, {
    required DashboardSection section,
    required Widget Function(T) data,
  }) {
    return switch (state) {
      SectionLoading<T>() => const StatTileSkeleton(),
      SectionData<T>(:final value) => data(value),
      SectionError<T>(:final error) => AppCard(
          padding: EdgeInsets.zero,
          child: ErrorView(
            message: _messageFor(error),
            onRetry: () => controller.retrySection(section),
          ),
        ),
    };
  }

  StatTile _runningTile(List<JobSummary> jobs) {
    final int running = jobs.where((JobSummary job) => job.isRunning).length;
    return StatTile(
      value: '$running',
      label: 'Running jobs',
      tone: StatusTone.warning,
      chip: running == 0
          ? null
          : const StatusChip(
              label: 'ACTIVE',
              icon: LucideIcons.activity,
              tone: StatusTone.warning,
            ),
    );
  }

  // ------------------------------------------------------------- latest ---

  Widget _latestSection(BuildContext context, DashboardStats stats, DashboardController controller) {
    final Widget heading = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        const LabelCaps(text: 'The ledger'),
        const SizedBox(height: 2),
        Text('Latest', style: Theme.of(context).textTheme.headlineSmall),
      ],
    );
    final Widget body = switch (stats.latest) {
      SectionLoading<List<LatestImage>>() => const LatestGridSkeleton(),
      SectionError<List<LatestImage>>(:final error) => ErrorView(
          message: _messageFor(error),
          onRetry: () => controller.retrySection(DashboardSection.latest),
        ),
      SectionData<List<LatestImage>>(:final value) when value.isEmpty => EmptyState(
          title: 'No images yet — start a batch',
          message: 'Run the pipeline once and the ledger fills up here.',
          action: PrimaryButton(
            label: 'New batch',
            onPressed: () => showAppToast(context, 'Batch wizard arrives with M4'),
          ),
        ),
      SectionData<List<LatestImage>>(:final value) => GridView.count(
          crossAxisCount: 2,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          mainAxisSpacing: AppSpacing.md,
          crossAxisSpacing: AppSpacing.md,
          childAspectRatio: 1,
          children: <Widget>[
            for (final LatestImage image in value) _latestTile(context, image),
          ],
        ),
    };
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[heading, const SizedBox(height: AppSpacing.md), body],
    );
  }

  Widget _latestTile(BuildContext context, LatestImage image) {
    return Semantics(
      button: true,
      label: image.title ?? image.filename,
      child: GestureDetector(
        onTap: () => showAppToast(context, 'Detail arrives with M3'),
        child: ClipRRect(
          borderRadius: const BorderRadius.all(Radius.circular(AppRadii.sm)),
          child: image.hasThumbnail
              ? Thumbnail(path: image.thumbnailPath!)
              : const ColoredBox(
                  color: AppColors.parchment200,
                  child: Center(
                    child: Icon(LucideIcons.imageOff, size: 24, color: AppColors.ink400),
                  ),
                ),
        ),
      ),
    );
  }

  // -------------------------------------------------------- running job ---

  Widget _runningJobCard(BuildContext context, JobSummary job) {
    // A fresh job can report 0 progress — slide until a real fraction exists.
    final double? fraction = job.total > 0 && job.progress > 0 ? job.progress : null;
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Row(
            children: <Widget>[
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      job.displayName,
                      style: Theme.of(context).textTheme.titleMedium,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 2),
                    LabelCaps(text: '${job.processed} of ${job.total} · ${job.stage}'),
                  ],
                ),
              ),
              const SizedBox(width: AppSpacing.md),
              const LiveDot(label: 'RUNNING'),
            ],
          ),
          const SizedBox(height: AppSpacing.md),
          ProgressBar(value: fraction),
        ],
      ),
    );
  }

  String? _messageFor(Object error) => switch (error) {
        AppException() => uiMessageFor(error),
        _ => null,
      };
}
