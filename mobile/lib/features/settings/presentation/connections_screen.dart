import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:lucide_flutter/lucide_flutter.dart';

import '../../../app/theme/tokens.dart';
import '../../../core/widgets/app_card.dart';
import '../../../core/widgets/connection_profile_banner.dart';
import '../../../core/widgets/stamp_badge.dart';
import '../../../core/widgets/status_chip.dart';
import '../../../core/widgets/toast_exception.dart';
import '../data/profile_store.dart';
import '../domain/connection_profile.dart';
import 'settings_controller.dart';

/// `/more/connections` — profile list (05 §2.9.1): active card carries a
/// brass check + `ACTIVE` stamp, tap opens the editor, swipe-left deletes
/// behind a confirm (never the active profile; the store re-seeds so the
/// list can never empty), and the `+` action adds one.
class ConnectionsScreen extends ConsumerStatefulWidget {
  const ConnectionsScreen({super.key});

  @override
  ConsumerState<ConnectionsScreen> createState() =>
      _ConnectionsScreenState();
}

class _ConnectionsScreenState extends ConsumerState<ConnectionsScreen> {
  /// Bumped after every editor round-trip or delete — [ProfileStore] is a
  /// plain synchronous store, so the list re-reads it on the next build.
  int _reloadTick = 0;

  List<ConnectionProfile> _profiles() =>
      ref.read(profileStoreProvider).profiles();

  Future<void> _openEditor(String profileId) async {
    await context.push<String>('/more/connections/$profileId');
    if (mounted) {
      setState(() => _reloadTick++);
    }
  }

  Future<void> _add() async {
    await context.push<String>('/more/connections/new');
    if (mounted) {
      setState(() => _reloadTick++);
    }
  }

  /// Swipe guard: blocked for the active profile (toast, card snaps back),
  /// ConfirmDialog otherwise; the actual removal runs in `onDismissed`.
  Future<bool?> _confirmDismiss(
    DismissDirection direction,
    ConnectionProfile profile,
    bool isActive,
  ) async {
    if (isActive) {
      showAppToast(
        context,
        "Can't delete the active profile — activate another one first.",
        tone: ToastTone.warning,
      );
      return false;
    }
    final bool? confirmed = await showDialog<bool>(
      context: context,
      builder: (BuildContext dialogContext) => AlertDialog(
        title: const Text('Delete profile?'),
        content: Text('Remove "${profile.label}" (${profile.baseUrl})?'),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    return confirmed ?? false;
  }

  Future<void> _onDismissed(ConnectionProfile profile) async {
    final String? blocked =
        await ref.read(profileSwitchHandlerProvider).deleteProfile(profile.id);
    if (!mounted) {
      return;
    }
    if (blocked != null) {
      showAppToast(context, blocked, tone: ToastTone.warning);
    } else {
      showAppToast(
        context,
        'Profile removed.',
        tone: ToastTone.success,
      );
    }
    setState(() => _reloadTick++);
  }

  @override
  Widget build(BuildContext context) {
    // Rebuild whenever the active profile flips (Activate from the editor);
    // `setState` after editor round-trips re-reads the store below.
    ref.watch(activeProfileProvider);
    final List<ConnectionProfile> profiles = _profiles();
    final String activeId = ref.read(activeProfileProvider).id;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Connections'),
        actions: <Widget>[
          IconButton(
            tooltip: 'Add profile',
            constraints: const BoxConstraints(minWidth: 48, minHeight: 48),
            onPressed: _add,
            icon: const Icon(LucideIcons.plus),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: <Widget>[
            const ConnectionProfileBanner(),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.all(AppSpacing.lg),
                children: <Widget>[
                  for (final ConnectionProfile profile in profiles)
                    Padding(
                      padding: const EdgeInsets.only(bottom: AppSpacing.md),
                      child: _ProfileCard(
                        profile: profile,
                        isActive: profile.id == activeId,
                        onOpen: () => _openEditor(profile.id),
                        confirmDismiss: (DismissDirection direction) =>
                            _confirmDismiss(
                          direction,
                          profile,
                          profile.id == activeId,
                        ),
                        onDismissed: () => _onDismissed(profile),
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// One profile card inside a [Dismissible] row.
class _ProfileCard extends StatelessWidget {
  const _ProfileCard({
    required this.profile,
    required this.isActive,
    required this.onOpen,
    required this.confirmDismiss,
    required this.onDismissed,
  });

  final ConnectionProfile profile;
  final bool isActive;
  final VoidCallback onOpen;
  final ConfirmDismissCallback confirmDismiss;
  final VoidCallback onDismissed;

  StatusChip? get _statusChip {
    final String? status = profile.lastStatus;
    if (status == null || status.isEmpty) {
      return null;
    }
    final bool ok = status == 'ok';
    return StatusChip(
      label: ok ? 'OK' : 'DOWN',
      icon: ok ? LucideIcons.circleCheck : LucideIcons.circleX,
      tone: ok ? StatusTone.success : StatusTone.failure,
    );
  }

  @override
  Widget build(BuildContext context) {
    final TextTheme textTheme = Theme.of(context).textTheme;
    return Dismissible(
      key: ValueKey<String>('profile-${profile.id}'),
      direction: DismissDirection.endToStart,
      confirmDismiss: confirmDismiss,
      onDismissed: (_) => onDismissed(),
      background: Container(
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
        decoration: const BoxDecoration(
          color: AppColors.oxblood600,
          borderRadius: BorderRadius.all(Radius.circular(AppRadii.sm)),
        ),
        child: const Icon(LucideIcons.trash2, color: AppColors.ink50),
      ),
      child: AppCard(
        padding: EdgeInsets.zero,
        child: InkWell(
          onTap: onOpen,
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 64),
            child: Padding(
              padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.lg,
                vertical: AppSpacing.md,
              ),
              child: Row(
                children: <Widget>[
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text(
                          profile.label,
                          style: textTheme.bodyMedium
                              ?.copyWith(color: AppColors.ink800),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          profile.baseUrl,
                          style: textTheme.bodySmall
                              ?.copyWith(color: AppColors.ink400),
                        ),
                      ],
                    ),
                  ),
                  if (_statusChip != null) ...<Widget>[
                    const SizedBox(width: AppSpacing.sm),
                    _statusChip!,
                  ],
                  if (isActive) ...<Widget>[
                    const SizedBox(width: AppSpacing.sm),
                    const Icon(
                      LucideIcons.check,
                      size: 20,
                      color: AppColors.brass400,
                      semanticLabel: 'Active profile',
                    ),
                    const SizedBox(width: AppSpacing.xs),
                    const StampBadge(label: 'ACTIVE', tone: StampTone.accent),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
