import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:lucide_flutter/lucide_flutter.dart';

import '../../../app/theme/tokens.dart';
import '../../../core/widgets/app_card.dart';
import '../../../core/widgets/connection_profile_banner.dart';
import '../../../core/widgets/label_caps.dart';
import '../../../core/widgets/toast_exception.dart';
import '../data/profile_store.dart';
import '../domain/connection_profile.dart';
import 'about_screen.dart';
import 'settings_controller.dart';

/// `/more` — the settings hub (05 §2.9): AppCard **row groups**, not a form
/// dump. Connections / Account / App / About push their sub-screens
/// (top-level routes, tabs hidden); the platform-switch row returns to `/hub`.
class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  String _activeCaption(WidgetRef ref) {
    final ConnectionProfile active = ref.watch(activeProfileProvider);
    final String? host = Uri.tryParse(active.baseUrl)?.host;
    return host == null || host.isEmpty
        ? active.label
        : '${active.label} · $host';
  }

  Future<void> _clearCache(BuildContext context, WidgetRef ref) async {
    await ref.read(clearImageCacheProvider)();
    if (context.mounted) {
      showAppToast(
        context,
        'Image cache cleared.',
        tone: ToastTone.success,
      );
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final bool reducedMotion = ref.watch(forceReducedMotionProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(AppSpacing.lg),
          children: <Widget>[
            const ConnectionProfileBanner(),
            const SizedBox(height: AppSpacing.lg),
            const LabelCaps(text: 'Connections'),
            const SizedBox(height: AppSpacing.sm),
            AppCard(
              padding: EdgeInsets.zero,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: <Widget>[
                  _NavRow(
                    icon: LucideIcons.plug,
                    title: 'Connection profiles',
                    caption: _activeCaption(ref),
                    onTap: () => context.push('/more/connections'),
                  ),
                  const _RowDivider(),
                  _NavRow(
                    icon: LucideIcons.activity,
                    title: 'Network diagnostics',
                    caption: 'Layer-by-layer reachability checks',
                    onTap: () => context.push('/diagnostics'),
                  ),
                ],
              ),
            ),
            const SizedBox(height: AppSpacing.xl),
            const LabelCaps(text: 'Account'),
            const SizedBox(height: AppSpacing.sm),
            AppCard(
              padding: EdgeInsets.zero,
              child: _NavRow(
                icon: LucideIcons.userRound,
                title: 'Account & gateway',
                caption: 'Local session · one seat',
                onTap: () => context.push('/more/account'),
              ),
            ),
            const SizedBox(height: AppSpacing.xl),
            const LabelCaps(text: 'App'),
            const SizedBox(height: AppSpacing.sm),
            AppCard(
              padding: EdgeInsets.zero,
              child: Column(
                children: <Widget>[
                  _NavRow(
                    icon: LucideIcons.accessibility,
                    title: 'Reduced motion',
                    caption: 'Freeze transitions & stamp animations',
                    trailing: Switch(
                      value: reducedMotion,
                      onChanged: (bool value) => ref
                          .read(forceReducedMotionProvider.notifier)
                          .set(value),
                    ),
                  ),
                  const _RowDivider(),
                  _NavRow(
                    icon: LucideIcons.images,
                    title: 'Clear image cache',
                    caption: 'Drop cached thumbnails & previews',
                    onTap: () => _clearCache(context, ref),
                  ),
                ],
              ),
            ),
            const SizedBox(height: AppSpacing.xl),
            const LabelCaps(text: 'About'),
            const SizedBox(height: AppSpacing.sm),
            AppCard(
              padding: EdgeInsets.zero,
              child: _NavRow(
                icon: LucideIcons.info,
                title: 'About',
                caption: 'Version $kAppVersion · licenses · diagnostics',
                onTap: () => context.push('/more/about'),
              ),
            ),
            const SizedBox(height: AppSpacing.xl),
            AppCard(
              padding: EdgeInsets.zero,
              child: _NavRow(
                icon: LucideIcons.layoutGrid,
                title: 'Switch platform',
                caption: 'Pick another stock marketplace workspace',
                onTap: () => context.go('/hub'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// One tappable settings row: icon, title + caption stack, chevron or a
/// custom trailing control; ≥48 dp (04 §4).
class _NavRow extends StatelessWidget {
  const _NavRow({
    required this.icon,
    required this.title,
    required this.caption,
    this.onTap,
    this.trailing,
  });

  final IconData icon;
  final String title;
  final String caption;
  final VoidCallback? onTap;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final TextTheme textTheme = Theme.of(context).textTheme;
    return InkWell(
      onTap: onTap,
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: 56),
        child: Padding(
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.lg,
            vertical: AppSpacing.sm,
          ),
          child: Row(
            children: <Widget>[
              Icon(icon, size: 20, color: AppColors.brass400),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      title,
                      style: textTheme.bodyMedium
                          ?.copyWith(color: AppColors.ink800),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      caption,
                      style: textTheme.bodySmall
                          ?.copyWith(color: AppColors.ink400),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              trailing ??
                  const Icon(
                    LucideIcons.chevronRight,
                    size: 18,
                    color: AppColors.ink400,
                  ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Hairline between rows inside one AppCard group.
class _RowDivider extends StatelessWidget {
  const _RowDivider();

  @override
  Widget build(BuildContext context) => Divider(
        height: 1,
        indent: AppSpacing.lg,
        endIndent: AppSpacing.lg,
        color: AppColors.parchment400,
      );
}
