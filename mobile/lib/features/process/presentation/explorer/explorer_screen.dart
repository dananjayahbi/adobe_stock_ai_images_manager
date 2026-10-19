import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_flutter/lucide_flutter.dart';

import '../../../../app/theme/tokens.dart';
import '../../../../core/network/session_cookie.dart';
import '../../../../core/widgets/app_card.dart';
import '../../../../core/widgets/empty_state.dart';
import '../../../../core/widgets/error_view.dart';
import '../../../../core/widgets/label_caps.dart';
import '../../../../core/widgets/skeleton_loader.dart';
import '../../domain/fs_repository.dart';
import '../batch_controller.dart';
import 'explorer_controller.dart';
import 'explorer_selection_bar.dart';

/// `/process/pick` — the source-folder image picker (M4).
///
/// CustomScrollView of three bands: breadcrumb row (first chip is
/// "Source"), folder cards grid (tap descends), and the image grid —
/// thumbs via `fsThumbUrl` + the session cookie, selection as a brass ring
/// + check overlay + name. The pinned [ExplorerSelectionBar] turns the
/// selection into a draft or a queued batch.
///
/// States: skeleton grid while the first load runs, `EmptyState` when the
/// source folder is unconfigured ([UnconfiguredSourceException]), [ErrorView]
/// + retry for everything else, an empty-folder note when the listing has
/// no dirs/files.
class ExplorerScreen extends ConsumerWidget {
  const ExplorerScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final AsyncValue<ExplorerState> async = ref.watch(
      explorerControllerProvider,
    );
    return Scaffold(
      appBar: AppBar(title: const Text('Select images')),
      body: Column(
        children: <Widget>[
          Expanded(child: _content(context, ref, async)),
        ],
      ),
      bottomNavigationBar: const ExplorerSelectionBar(),
    );
  }

  Widget _content(
    BuildContext context,
    WidgetRef ref,
    AsyncValue<ExplorerState> async,
  ) {
    if (async.isLoading && !async.hasValue) {
      return _skeletonGrid();
    }
    if (!async.hasValue) {
      final Object error = async.error ?? Exception('unknown');
      if (error is UnconfiguredSourceException) {
        return const EmptyState(
          title: 'Source folder not configured',
          message: 'Set it in the web app: Config → Source folder',
          icon: LucideIcons.folderOpen,
        );
      }
      return ErrorView(
        message: actionErrorText(error),
        onRetry: () => ref.read(explorerControllerProvider.notifier).retry(),
      );
    }
    final ExplorerState state = async.value!;
    final FsRepository repository = ref.watch(fsRepositoryProvider);
    final String? cookie = ref.watch(sessionCookieHeaderProvider);

    return CustomScrollView(
      physics: const AlwaysScrollableScrollPhysics(),
      slivers: <Widget>[
        SliverToBoxAdapter(child: _breadcrumbs(context, ref, state)),
        if (state.loading)
          const SliverToBoxAdapter(
            child: LinearProgressIndicator(minHeight: 2),
          ),
        if (state.dirs.isNotEmpty) ...<Widget>[
          const SliverPadding(
            padding: EdgeInsets.fromLTRB(
              AppSpacing.md,
              AppSpacing.sm,
              AppSpacing.md,
              AppSpacing.xs,
            ),
            sliver: SliverToBoxAdapter(child: LabelCaps(text: 'Folders')),
          ),
          SliverPadding(
            padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
            sliver: _folderGrid(context, ref, state),
          ),
        ],
        if (state.files.isNotEmpty) ...<Widget>[
          const SliverPadding(
            padding: EdgeInsets.fromLTRB(
              AppSpacing.md,
              AppSpacing.lg,
              AppSpacing.md,
              AppSpacing.xs,
            ),
            sliver: SliverToBoxAdapter(child: LabelCaps(text: 'Images')),
          ),
          SliverPadding(
            padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
            sliver: _imageGrid(ref, state, repository, cookie),
          ),
        ],
        if (state.dirs.isEmpty && state.files.isEmpty)
          const SliverFillRemaining(
            hasScrollBody: false,
            child: EmptyState(
              title: 'No images here',
              message: 'Pick another folder from the breadcrumb above.',
              icon: LucideIcons.folderOpen,
            ),
          ),
      ],
    );
  }

  // ------------------------------------------------------------ breadcrumb

  Widget _breadcrumbs(
    BuildContext context,
    WidgetRef ref,
    ExplorerState state,
  ) {
    final ExplorerController controller = ref.read(
      explorerControllerProvider.notifier,
    );
    return Padding(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.sm,
      ),
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: Row(
          children: <Widget>[
            if (state.parent != null)
              _crumb(
                context,
                label: '',
                icon: LucideIcons.arrowUp,
                current: false,
                onTap: () => controller.navigate(state.parent!),
              ),
            _crumb(
              context,
              label: 'Source',
              current: state.path.isEmpty,
              onTap: () => controller.navigate(''),
            ),
            for (int i = 0; i < state.segments.length; i++) ...<Widget>[
              _crumbDivider(),
              _crumb(
                context,
                label: state.segments[i],
                current: i == state.segments.length - 1,
                onTap: () => controller.navigate(
                  state.segments.sublist(0, i + 1).join('/'),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _crumbDivider() => const Padding(
    padding: EdgeInsets.symmetric(horizontal: AppSpacing.xs),
    child: Icon(LucideIcons.chevronRight, size: 14, color: AppColors.ink400),
  );

  /// One breadcrumb chip; [current] lights it brass. An empty [label] with
  /// an [icon] renders the "up one level" affordance.
  Widget _crumb(
    BuildContext context, {
    required String label,
    required bool current,
    required VoidCallback onTap,
    IconData? icon,
  }) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(AppRadii.sm),
        child: Container(
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.sm,
            vertical: AppSpacing.xs,
          ),
          decoration: BoxDecoration(
            color: current ? AppColors.brass700 : AppColors.parchment200,
            borderRadius: BorderRadius.circular(AppRadii.sm),
            border: Border.all(
              color: current ? AppColors.brass400 : AppColors.parchment300,
            ),
          ),
          child: icon != null
              ? Icon(icon, size: 14, color: AppColors.ink600)
              : Text(
                  label,
                  style: Theme.of(context).textTheme.labelSmall?.copyWith(
                    color: current ? AppColors.brass300 : AppColors.ink600,
                    fontWeight: FontWeight.w600,
                  ),
                ),
        ),
      ),
    );
  }

  // ----------------------------------------------------------------- grid

  Widget _folderGrid(BuildContext context, WidgetRef ref, ExplorerState state) {
    final ExplorerController controller = ref.read(
      explorerControllerProvider.notifier,
    );
    return SliverGrid(
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 3,
        mainAxisSpacing: AppSpacing.sm,
        crossAxisSpacing: AppSpacing.sm,
        childAspectRatio: 2.1,
      ),
      delegate: SliverChildBuilderDelegate((BuildContext context, int index) {
        final String name = state.dirs[index];
        return Semantics(
          button: true,
          label: 'Folder $name',
          child: InkWell(
            onTap: () => controller.navigate(state.relPath(name)),
            borderRadius: BorderRadius.circular(AppRadii.md),
            child: AppCard(
              padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm),
              child: Row(
                children: <Widget>[
                  const Icon(
                    LucideIcons.folder,
                    size: 18,
                    color: AppColors.brass400,
                  ),
                  const SizedBox(width: AppSpacing.xs),
                  Expanded(
                    child: Text(
                      name,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodySmall
                          ?.copyWith(color: AppColors.ink800),
                    ),
                  ),
                  const Icon(
                    LucideIcons.chevronRight,
                    size: 16,
                    color: AppColors.ink400,
                  ),
                ],
              ),
            ),
          ),
        );
      }, childCount: state.dirs.length),
    );
  }

  Widget _imageGrid(
    WidgetRef ref,
    ExplorerState state,
    FsRepository repository,
    String? cookie,
  ) {
    final ExplorerController controller = ref.read(
      explorerControllerProvider.notifier,
    );
    return SliverGrid(
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 3,
        mainAxisSpacing: AppSpacing.sm,
        crossAxisSpacing: AppSpacing.sm,
        childAspectRatio: 0.78,
      ),
      delegate: SliverChildBuilderDelegate((BuildContext context, int index) {
        final FsFile file = state.files[index];
        final String rel = state.relPath(file.name);
        final bool selected = state.selected.contains(rel);
        return Semantics(
          button: true,
          selected: selected,
          label: file.name,
          child: InkWell(
            onTap: () => controller.toggle(file.name),
            borderRadius: BorderRadius.circular(AppRadii.sm),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                Expanded(
                  child: Stack(
                    fit: StackFit.expand,
                    children: <Widget>[
                      ClipRRect(
                        borderRadius: BorderRadius.circular(AppRadii.sm),
                        child: Image.network(
                          '${state.thumbBase}${repository.thumbUrl(rel)}',
                          fit: BoxFit.cover,
                          headers: cookie == null
                              ? null
                              : <String, String>{'Cookie': cookie},
                          errorBuilder:
                              (
                                BuildContext context,
                                Object error,
                                StackTrace? stackTrace,
                              ) => const ColoredBox(
                                color: AppColors.parchment200,
                                child: Center(
                                  child: Icon(
                                    LucideIcons.image,
                                    size: 24,
                                    color: AppColors.ink400,
                                  ),
                                ),
                              ),
                        ),
                      ),
                      if (selected)
                        Positioned.fill(
                          child: DecoratedBox(
                            decoration: BoxDecoration(
                              borderRadius: BorderRadius.circular(AppRadii.sm),
                              border: Border.all(
                                color: AppColors.brass400,
                                width: 3,
                              ),
                            ),
                          ),
                        ),
                      if (selected)
                        Positioned(
                          top: AppSpacing.xs,
                          right: AppSpacing.xs,
                          child: Container(
                            padding: const EdgeInsets.all(3),
                            decoration: const BoxDecoration(
                              color: AppColors.brass500,
                              shape: BoxShape.circle,
                            ),
                            child: const Icon(
                              LucideIcons.check,
                              size: 12,
                              color: AppColors.ink900,
                            ),
                          ),
                        ),
                    ],
                  ),
                ),
                const SizedBox(height: AppSpacing.xs),
                Text(
                  file.name,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.labelSmall?.copyWith(
                    color: selected ? AppColors.brass300 : AppColors.ink400,
                  ),
                ),
              ],
            ),
          ),
        );
      }, childCount: state.files.length),
    );
  }

  // -------------------------------------------------------------- loading

  Widget _skeletonGrid() => GridView.builder(
    padding: const EdgeInsets.all(AppSpacing.md),
    physics: const NeverScrollableScrollPhysics(),
    gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
      crossAxisCount: 3,
      mainAxisSpacing: AppSpacing.sm,
      crossAxisSpacing: AppSpacing.sm,
      childAspectRatio: 0.78,
    ),
    itemCount: 9,
    itemBuilder: (BuildContext context, int index) => const SkeletonLoader(),
  );
}
