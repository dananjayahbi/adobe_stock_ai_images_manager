import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_flutter/lucide_flutter.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../app/theme/tokens.dart';
import '../../../core/config/app_config.dart';
import '../../../core/widgets/app_card.dart';
import '../../../core/widgets/connection_profile_banner.dart';
import '../../../core/widgets/label_caps.dart';
import '../../../core/widgets/primary_button.dart';
import '../../../core/widgets/secondary_button.dart';
import '../../../core/widgets/status_chip.dart';
import '../../../core/widgets/toast_exception.dart';
import '../../platforms/presentation/platforms_controller.dart';
import '../data/health_api.dart';
import '../data/profile_store.dart';
import '../domain/connection_profile.dart';

/// Single source of truth for the version line (mirrors `pubspec.yaml`
/// `version:` — keep the two in step manually; no pubspec edits, 07 M5).
const String kAppVersion = '1.0.0+1';

/// `/more/about` — version, licenses, diagnostics (05 §2.9.3).
class AboutScreen extends ConsumerWidget {
  const AboutScreen({super.key});

  Future<void> _copyDiagnostics(
    BuildContext context, {
    required String platformId,
    required String baseUrl,
    required String tunnelHost,
  }) async {
    final String lines = <String>[
      'app_version: $kAppVersion',
      'platform_id: $platformId',
      'active_profile: $baseUrl',
      'tunnel_host: $tunnelHost',
    ].join('\n');
    await Clipboard.setData(ClipboardData(text: lines));
    if (context.mounted) {
      showAppToast(context, 'Diagnostics copied.', tone: ToastTone.success);
    }
  }

  Future<void> _openDashboard(BuildContext context, String baseUrl) async {
    final Uri? uri = Uri.tryParse(baseUrl);
    if (uri == null || !uri.hasScheme) {
      return;
    }
    try {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    } on Object {
      if (context.mounted) {
        showAppToast(
          context,
          'Could not open the web dashboard.',
          tone: ToastTone.error,
        );
      }
    }
  }

  String _tunnelHost() =>
      Uri.tryParse(AppConfig.tunnelBaseUrl)?.host ?? AppConfig.tunnelBaseUrl;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ConnectionProfile active = ref.watch(activeProfileProvider);
    final String platformId = ref.watch(activePlatformIdProvider);
    final AsyncValue<bool> health = ref.watch(activeHealthProvider);
    final TextTheme textTheme = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(title: const Text('About')),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(AppSpacing.lg),
          children: <Widget>[
            const ConnectionProfileBanner(),
            const SizedBox(height: AppSpacing.lg),
            AppCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    'AI Stock Studio',
                    style: textTheme.titleMedium?.copyWith(
                      color: AppColors.ink800,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: AppSpacing.xs),
                  Text(
                    'Version $kAppVersion',
                    style: textTheme.bodyMedium
                        ?.copyWith(color: AppColors.ink400),
                  ),
                  const SizedBox(height: AppSpacing.md),
                  Text(
                    'Local studio remote control — FastAPI backend, '
                    'per-profile connections, one seat per device.',
                    style: textTheme.bodySmall?.copyWith(
                      color: AppColors.ink400,
                      height: 1.5,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: AppSpacing.xl),
            const LabelCaps(text: 'Diagnostics'),
            const SizedBox(height: AppSpacing.sm),
            AppCard(
              padding: EdgeInsets.zero,
              child: Column(
                children: <Widget>[
                  _InfoRow(label: 'Platform', value: platformId),
                  const _RowDivider(),
                  _InfoRow(label: 'Active profile', value: active.baseUrl),
                  const _RowDivider(),
                  _InfoRow(label: 'Tunnel host', value: _tunnelHost()),
                  const _RowDivider(),
                  _InfoRow(
                    label: 'Backend health',
                    trailing: health.when(
                      loading: () => const StatusChip(
                        label: 'CHECKING',
                        icon: LucideIcons.circleDashed,
                        tone: StatusTone.neutral,
                      ),
                      error: (_, _) => const StatusChip(
                        label: 'OFFLINE',
                        icon: LucideIcons.circleX,
                        tone: StatusTone.failure,
                      ),
                      data: (bool ok) => StatusChip(
                        label: ok ? 'ONLINE' : 'OFFLINE',
                        icon: ok
                            ? LucideIcons.circleCheck
                            : LucideIcons.circleX,
                        tone: ok ? StatusTone.success : StatusTone.failure,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: AppSpacing.lg),
            SecondaryButton(
              label: 'Copy diagnostics',
              expanded: true,
              onPressed: () => _copyDiagnostics(
                context,
                platformId: platformId,
                baseUrl: active.baseUrl,
                tunnelHost: _tunnelHost(),
              ),
            ),
            const SizedBox(height: AppSpacing.sm),
            PrimaryButton(
              label: 'Open web dashboard',
              expanded: true,
              onPressed: () => _openDashboard(context, active.baseUrl),
            ),
            const SizedBox(height: AppSpacing.xl),
            const LabelCaps(text: 'Licenses'),
            const SizedBox(height: AppSpacing.sm),
            AppCard(
              padding: EdgeInsets.zero,
              child: InkWell(
                onTap: () => showLicensePage(
                  context: context,
                  applicationName: 'AI Stock Studio',
                  applicationVersion: kAppVersion,
                  applicationIcon: const Icon(
                    LucideIcons.images,
                    size: 32,
                    color: AppColors.brass400,
                  ),
                ),
                child: ConstrainedBox(
                  constraints: const BoxConstraints(minHeight: 56),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(
                      horizontal: AppSpacing.lg,
                      vertical: AppSpacing.sm,
                    ),
                    child: Row(
                      children: <Widget>[
                        const Icon(
                          LucideIcons.bookOpen,
                          size: 20,
                          color: AppColors.brass400,
                        ),
                        const SizedBox(width: AppSpacing.md),
                        Expanded(
                          child: Text(
                            'Open-source licenses',
                            style: textTheme.bodyMedium
                                ?.copyWith(color: AppColors.ink800),
                          ),
                        ),
                        const Icon(
                          LucideIcons.chevronRight,
                          size: 18,
                          color: AppColors.ink400,
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
    );
  }
}

/// Caption line + optional trailing chip for one diagnostic row.
class _InfoRow extends StatelessWidget {
  const _InfoRow({required this.label, this.value, this.trailing});

  final String label;
  final String? value;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final TextTheme textTheme = Theme.of(context).textTheme;
    return ConstrainedBox(
      constraints: const BoxConstraints(minHeight: 48),
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.lg,
          vertical: AppSpacing.sm,
        ),
        child: Row(
          children: <Widget>[
            Text(
              label,
              style: textTheme.bodyMedium?.copyWith(color: AppColors.ink400),
            ),
            const Spacer(),
            if (value != null)
              Flexible(
                child: Text(
                  value!,
                  textAlign: TextAlign.end,
                  overflow: TextOverflow.ellipsis,
                  style:
                      textTheme.bodySmall?.copyWith(color: AppColors.ink800),
                ),
              ),
            if (trailing != null) ...<Widget>[
              const SizedBox(width: AppSpacing.sm),
              trailing!,
            ],
          ],
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
