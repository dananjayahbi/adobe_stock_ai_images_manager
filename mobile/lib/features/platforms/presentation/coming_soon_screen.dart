import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:lucide_flutter/lucide_flutter.dart';

import '../../../app/theme/tokens.dart';
import '../../../core/utils/app_exception.dart';
import '../../../core/utils/ui_message.dart';
import '../../../core/widgets/app_card.dart';
import '../../../core/widgets/error_view.dart';
import '../../../core/widgets/label_caps.dart';
import '../../../core/widgets/secondary_button.dart';
import '../../../core/widgets/skeleton_loader.dart';
import '../../../core/widgets/stamp_badge.dart';
import '../../../core/widgets/stamp_in.dart';
import '../domain/platform.dart';
import 'platforms_controller.dart';

/// `/coming-soon/:platformId` — generic shell for platforms whose pipeline
/// hasn't landed (05 §2.10), parity with web `PlatformComingSoon`.
///
/// Fetches `GET /api/platforms/{platform_id}` directly (metadata endpoint,
/// **not** `platformPath` — that seam scopes data APIs only). Unknown ids
/// 404 into an inline [ErrorView] with back.
class ComingSoonScreen extends ConsumerWidget {
  const ComingSoonScreen({super.key, required this.platformId});

  /// Route parameter from `/coming-soon/:platformId`.
  final String platformId;

  static const List<String> _features = <String>[
    'Upload & ingest',
    'Batch processing pipeline',
    'Review & approval flow',
    'Delivery export',
  ];

  void _back(BuildContext context) {
    if (context.canPop()) {
      context.pop();
    } else {
      context.go('/hub');
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final AsyncValue<PlatformEntry> entry =
        ref.watch(platformProvider(platformId));

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 560),
            child: Padding(
              padding: const EdgeInsets.all(AppSpacing.lg),
              child: entry.when(
                loading: () => Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: <Widget>[
                    const SkeletonLoader(height: 120),
                    const SizedBox(height: AppSpacing.md),
                    const SkeletonLoader(height: 56),
                  ],
                ),
                error: (Object error, StackTrace stackTrace) => Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    ErrorView(
                      message: error is AppException
                          ? uiMessageFor(error)
                          : 'Something went wrong.',
                      onRetry: () =>
                          ref.invalidate(platformProvider(platformId)),
                    ),
                    const SizedBox(height: AppSpacing.lg),
                    SecondaryButton(
                      label: 'Back to platforms',
                      onPressed: () => _back(context),
                    ),
                  ],
                ),
                data: (PlatformEntry platform) => _body(
                  context,
                  ref,
                  platform,
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _body(
    BuildContext context,
    WidgetRef ref,
    PlatformEntry platform,
  ) {
    final TextTheme textTheme = Theme.of(context).textTheme;
    return SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          AppCard(
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.xl,
              vertical: AppSpacing.xxl,
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                // Wow-stamp entrance: rotated "IN THE WORKS" postmark.
                StampIn(
                  delay: const Duration(milliseconds: 120),
                  child: const StampBadge(
                    label: 'In the works',
                    tone: StampTone.accent,
                    rotation: -8,
                  ),
                ),
                const SizedBox(height: AppSpacing.xl),
                Text(
                  platform.name,
                  textAlign: TextAlign.center,
                  style: (textTheme.displaySmall ?? const TextStyle())
                      .copyWith(color: AppColors.ink800),
                ),
                const SizedBox(height: AppSpacing.sm),
                Text(
                  platform.tagline,
                  textAlign: TextAlign.center,
                  style: (textTheme.bodyMedium ?? const TextStyle()).copyWith(
                    color: AppColors.oxblood300,
                    fontStyle: FontStyle.italic,
                    height: 1.5,
                  ),
                ),
                const SizedBox(height: AppSpacing.xl),
                const SizedBox(
                  width: 160,
                  child: Divider(height: 1, color: AppColors.parchment400),
                ),
                const SizedBox(height: AppSpacing.xl),
                const LabelCaps(text: 'Planned for this workspace'),
                const SizedBox(height: AppSpacing.md),
                ..._features.map(
                  (String feature) => Padding(
                    padding: const EdgeInsets.symmetric(
                      vertical: AppSpacing.xs,
                    ),
                    child: Row(
                      children: [
                        const Icon(
                          LucideIcons.circleDashed,
                          size: 16,
                          color: AppColors.parchment700,
                        ),
                        const SizedBox(width: AppSpacing.sm),
                        Expanded(
                          child: Text(
                            feature,
                            style: (textTheme.bodySmall ?? const TextStyle())
                                .copyWith(
                                  color: AppColors.ink400,
                                  height: 1.43,
                                ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: AppSpacing.xl),
                SecondaryButton(
                  label: 'Back to platforms',
                  onPressed: () => _back(context),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
