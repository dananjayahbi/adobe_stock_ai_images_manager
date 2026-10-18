import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/theme/tokens.dart';
import '../../../core/utils/app_exception.dart';
import '../../../core/utils/ui_message.dart';
import '../../../core/widgets/app_card.dart';
import '../../../core/widgets/error_view.dart';
import '../../../core/widgets/label_caps.dart';
import '../../../core/widgets/skeleton_loader.dart';
import '../domain/platform.dart';
import 'platform_card.dart';
import 'platforms_controller.dart';

/// `/hub` — the master Platform Hub (05 §2.3), parity with the web
/// `PlatformPicker`: hero card, responsive card grid, pull-to-refresh.
///
/// Lives outside the shell; choosing a platform is a global act — available
/// cards select + `go('/home')`, the rest push `/coming-soon/:id`.
class PlatformHubScreen extends ConsumerWidget {
  const PlatformHubScreen({super.key});

  Future<void> _refresh(WidgetRef ref) {
    ref.invalidate(platformsProvider);
    return ref.read(platformsProvider.future);
  }

  void _open(WidgetRef ref, PlatformEntry platform, BuildContext context) {
    if (platform.available) {
      ref.read(activePlatformIdProvider.notifier).select(platform.id);
      if (context.mounted) {
        context.go('/home');
      }
    } else {
      context.push('/coming-soon/${platform.id}');
    }
  }

  String _messageFor(Object error) => error is AppException
      ? uiMessageFor(error)
      : 'Something went wrong.';

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final AsyncValue<List<PlatformEntry>> catalog =
        ref.watch(platformsProvider);

    return Scaffold(
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: () => _refresh(ref),
          child: ListView(
            padding: const EdgeInsets.all(AppSpacing.lg),
            children: [
              _hero(context),
              const SizedBox(height: AppSpacing.xl),
              ..._catalog(context, ref, catalog),
            ],
          ),
        ),
      ),
    );
  }

  /// Eyebrow + Playfair title card with script ✦ corners (05 §2.3).
  Widget _hero(BuildContext context) {
    final TextTheme textTheme = Theme.of(context).textTheme;
    return AppCard(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.xl,
        vertical: AppSpacing.xxl,
      ),
      child: Stack(
        children: [
          const Positioned(
            left: 4,
            top: 0,
            child: _Flourish(),
          ),
          const Positioned(
            right: 4,
            bottom: 0,
            child: _Flourish(),
          ),
          Column(
            children: [
              const LabelCaps(text: 'AI Stock Studio'),
              const SizedBox(height: AppSpacing.sm),
              Text(
                'Where are today\u2019s images going?',
                textAlign: TextAlign.center,
                style: (textTheme.displaySmall ?? const TextStyle())
                    .copyWith(color: AppColors.ink800),
              ),
              const SizedBox(height: AppSpacing.md),
              Text(
                'One studio, every marketplace \u2014 pick a destination '
                'and the pipeline follows.',
                textAlign: TextAlign.center,
                style: (textTheme.bodyMedium ?? const TextStyle()).copyWith(
                  color: AppColors.ink400,
                  height: 1.5,
                ),
              ),
              const SizedBox(height: AppSpacing.lg),
              const LabelCaps(text: 'Choose a workspace'),
            ],
          ),
        ],
      ),
    );
  }

  /// Loading → hero-adjacent card skeletons; error/offline → [ErrorView]
  /// with retry; empty → inline notice; data → the responsive grid.
  List<Widget> _catalog(
    BuildContext context,
    WidgetRef ref,
    AsyncValue<List<PlatformEntry>> catalog,
  ) {
    return catalog.when(
      loading: () => const <Widget>[
        SkeletonLoader(height: 120),
        SizedBox(height: AppSpacing.md),
        SkeletonLoader(height: 120),
        SizedBox(height: AppSpacing.md),
        SkeletonLoader(height: 120),
      ],
      error: (Object error, StackTrace stackTrace) => <Widget>[
        ErrorView(
          message: _messageFor(error),
          onRetry: () => _refresh(ref),
        ),
      ],
      data: (List<PlatformEntry> platforms) {
        if (platforms.isEmpty) {
          return <Widget>[
            const ErrorView(message: 'No workspaces are registered yet.'),
          ];
        }
        return <Widget>[_grid(context, ref, platforms)];
      },
    );
  }

  /// 2 columns ≥600 dp, 1 column below (05 §2.3) with ~60 ms stagger.
  ///
  /// A [Wrap] (not a grid with a fixed aspect ratio) so taglines of any
  /// length size their own card height — no clipping on narrow phones.
  Widget _grid(
    BuildContext context,
    WidgetRef ref,
    List<PlatformEntry> platforms,
  ) {
    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints constraints) {
        final int columns = constraints.maxWidth >= 600 ? 2 : 1;
        const double spacing = AppSpacing.md;
        final double cardWidth =
            (constraints.maxWidth - spacing * (columns - 1)) / columns;
        return Wrap(
          spacing: spacing,
          runSpacing: spacing,
          children: <Widget>[
            for (int i = 0; i < platforms.length; i++)
              SizedBox(
                width: cardWidth,
                child: PlatformCard(
                  platform: platforms[i],
                  entranceDelay: Duration(milliseconds: 60 * i),
                  onTap: () => _open(ref, platforms[i], context),
                ),
              ),
          ],
        );
      },
    );
  }
}

/// Script ✦ corner flourish, brass at 50% (web hero parity).
class _Flourish extends StatelessWidget {
  const _Flourish();

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: Text(
        '\u2726',
        style: Theme.of(context).textTheme.headlineLarge?.copyWith(
          color: AppColors.brass400.withValues(alpha: 0.5),
        ),
      ),
    );
  }
}
