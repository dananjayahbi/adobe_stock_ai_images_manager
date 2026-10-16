import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_flutter/lucide_flutter.dart';

import '../../../app/theme/tokens.dart';
import '../../../core/widgets/label_caps.dart';
import '../../../core/widgets/toast_exception.dart';
import '../../settings/data/profile_store.dart';
import '../../settings/domain/connection_profile.dart';
import '../../settings/presentation/settings_controller.dart';
import 'login_address_editor.dart';

/// Pre-auth connection row for `/login`.
///
/// A fresh install defaults to the `localhost` profile, which is the device
/// itself on a phone — the session/platforms probes then fail and the form
/// offers no way out (everything connection-related lives behind auth).
/// This row shows the active profile and opens a **health-gated** picker, so
/// the studio is reachable *before* signing in; the full editor behind the
/// login keeps its richer actions (edit, add, delete).
class LoginProfileSwitcher extends ConsumerStatefulWidget {
  const LoginProfileSwitcher({super.key});

  @override
  ConsumerState<LoginProfileSwitcher> createState() =>
      _LoginProfileSwitcherState();
}

class _LoginProfileSwitcherState extends ConsumerState<LoginProfileSwitcher> {
  Future<void> _openPicker() async {
    final String? message = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(14)),
      ),
      builder: (_) => _ProfilePickerSheet(
        profiles: ref.read(profileStoreProvider).profiles(),
        activeId: ref.read(activeProfileProvider).id,
      ),
    );
    if (!mounted || message == null) return;
    showAppToast(context, message, tone: ToastTone.success);
  }

  /// `https://studio.hotelgo.lk` → `studio.hotelgo.lk` (port kept when set).
  static String _hostOf(String baseUrl) {
    final Uri? uri = Uri.tryParse(baseUrl.trim());
    if (uri == null || uri.host.isEmpty) return baseUrl;
    final int port = uri.hasPort ? uri.port : 0;
    return port == 0 ? uri.host : '${uri.host}:$port';
  }

  @override
  Widget build(BuildContext context) {
    final ConnectionProfile active = ref.watch(activeProfileProvider);
    final TextTheme textTheme = Theme.of(context).textTheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const LabelCaps(text: 'CONNECTION'),
        const SizedBox(height: AppSpacing.xs),
        InkWell(
          onTap: _openPicker,
          borderRadius: BorderRadius.circular(6),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 4),
            child: Row(
              children: [
                const Icon(
                  LucideIcons.plug,
                  size: 16,
                  color: AppColors.brass400,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(active.label, style: textTheme.titleSmall),
                      Text(
                        _hostOf(active.baseUrl),
                        style: textTheme.bodySmall?.copyWith(
                          color: AppColors.parchment700,
                        ),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                ),
                const Icon(
                  LucideIcons.chevronRight,
                  size: 18,
                  color: AppColors.parchment700,
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

/// Bottom-sheet list of profiles; activates via the health-gated handler and
/// only closes on success (a dead host keeps the sheet open with the reason
/// inline, mirroring the connection editor).
class _ProfilePickerSheet extends ConsumerStatefulWidget {
  const _ProfilePickerSheet({
    required this.profiles,
    required this.activeId,
  });

  final List<ConnectionProfile> profiles;
  final String activeId;

  @override
  ConsumerState<_ProfilePickerSheet> createState() =>
      _ProfilePickerSheetState();
}

class _ProfilePickerSheetState extends ConsumerState<_ProfilePickerSheet> {
  String? _busyId;
  String? _error;
  bool _editing = false;

  Future<void> _activate(ConnectionProfile profile) async {
    if (_busyId != null) return;
    setState(() {
      _busyId = profile.id;
      _error = null;
    });
    final SwitchOutcome outcome = await ref
        .read(profileSwitchHandlerProvider)
        .switchTo(profile.id);
    if (!mounted) return;
    if (outcome.ok) {
      Navigator.of(context).pop(
        outcome.latencyMs == null
            ? 'Already the active profile.'
            : 'Switched · ${outcome.latencyMs} ms',
      );
      return;
    }
    setState(() {
      _busyId = null;
      _error = outcome.error ?? 'Host unreachable.';
    });
  }

  ConnectionProfile get _activeProfile => widget.profiles.firstWhere(
        (ConnectionProfile p) => p.id == widget.activeId,
      );

  @override
  Widget build(BuildContext context) {
    final TextTheme textTheme = Theme.of(context).textTheme;
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.xl,
          0,
          AppSpacing.xl,
          AppSpacing.xl,
        ),
        // Scrollable with a cap: the list + error + edit link must fit even
        // on short surfaces (tests, small phones, open keyboards).
        child: ConstrainedBox(
          constraints: BoxConstraints(
            maxHeight: MediaQuery.sizeOf(context).height * 0.75,
          ),
          child: SingleChildScrollView(
            child: _editing
                ? LoginAddressEditor(
                    profile: _activeProfile,
                    onCancel: () => setState(() => _editing = false),
                    onSaved: (String message) =>
                        Navigator.of(context).pop(message),
                  )
                : Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const LabelCaps(text: 'SWITCH CONNECTION'),
                      const SizedBox(height: AppSpacing.md),
                      for (final ConnectionProfile profile in widget.profiles)
                        _ProfileRow(
                          profile: profile,
                          isActive: profile.id == widget.activeId,
                          busy: _busyId == profile.id,
                          onTap: () => _activate(profile),
                        ),
                      if (_error != null) ...[
                        const SizedBox(height: AppSpacing.sm),
                        Text(
                          _error!,
                          style: textTheme.bodySmall?.copyWith(
                            color: AppColors.rust400,
                          ),
                        ),
                      ],
                      const SizedBox(height: AppSpacing.sm),
                      // DNS escape hatch: raw IP needs no name resolution.
                      TextButton(
                        onPressed: () => setState(() => _editing = true),
                        style: TextButton.styleFrom(
                          alignment: Alignment.centerLeft,
                          padding: const EdgeInsets.symmetric(horizontal: 4),
                        ),
                        child: Text(
                          'Edit connection address…',
                          style: textTheme.bodySmall?.copyWith(
                            color: AppColors.brass400,
                            decoration: TextDecoration.underline,
                            decorationColor: AppColors.brass400,
                          ),
                        ),
                      ),
                      const SizedBox(height: AppSpacing.xs),
                      Text(
                        'Every switch is health-checked first — a dead host '
                        'keeps the current profile.',
                        style: textTheme.bodySmall?.copyWith(
                          color: AppColors.parchment700,
                        ),
                      ),
                    ],
                  ),
          ),
        ),
      ),
    );
  }
}

class _ProfileRow extends StatelessWidget {
  const _ProfileRow({
    required this.profile,
    required this.isActive,
    required this.busy,
    required this.onTap,
  });

  final ConnectionProfile profile;
  final bool isActive;
  final bool busy;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final TextTheme textTheme = Theme.of(context).textTheme;
    return InkWell(
      onTap: busy ? null : onTap,
      borderRadius: BorderRadius.circular(8),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 4),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(profile.label, style: textTheme.titleSmall),
                  Text(
                    profile.baseUrl,
                    style: textTheme.bodySmall?.copyWith(
                      color: AppColors.parchment700,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
            if (busy)
              const SizedBox(
                width: 16,
                height: 16,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            else if (isActive)
              const Icon(
                LucideIcons.circleCheck,
                size: 18,
                color: AppColors.brass400,
              ),
          ],
        ),
      ),
    );
  }
}
