import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/theme/tokens.dart';
import '../../../core/widgets/label_caps.dart';
import '../../../core/widgets/primary_button.dart';
import '../../../core/widgets/secondary_button.dart';
import '../../settings/data/health_api.dart';
import '../../settings/data/profile_store.dart';
import '../../settings/domain/connection_profile.dart';
import '../../settings/presentation/connection_editor_screen.dart';
import '../../settings/presentation/settings_controller.dart';

/// Inline "edit address" view hosted by the login profile picker.
///
/// The escape hatch for device-level DNS failures: a raw IP
/// (`http://192.168.x.x:8007`) needs no name resolution at all, so a phone
/// whose resolver can't see the tunnel hostname can still reach the studio
/// on the LAN. The new address is **verified before it is persisted** —
/// a dead URL never replaces a working one — and editing the active profile
/// republishes it so every request switches over immediately.
class LoginAddressEditor extends ConsumerStatefulWidget {
  const LoginAddressEditor({
    super.key,
    required this.profile,
    required this.onCancel,
    required this.onSaved,
  });

  final ConnectionProfile profile;

  /// Back to the picker list (address not changed).
  final VoidCallback onCancel;

  /// Verified + persisted — carries the toast message for the host sheet.
  final ValueChanged<String> onSaved;

  @override
  ConsumerState<LoginAddressEditor> createState() =>
      _LoginAddressEditorState();
}

class _LoginAddressEditorState extends ConsumerState<LoginAddressEditor> {
  late final TextEditingController _urlController;
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _urlController = TextEditingController(text: widget.profile.baseUrl);
  }

  @override
  void dispose() {
    _urlController.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (_busy) return;
    final String value = _urlController.text.trim();
    final String? validation = validateBaseUrl(value);
    if (validation != null) {
      setState(() => _error = validation);
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    // Verify first: a dead address must never replace the stored one.
    final HealthProbeResult probe =
        await ref.read(profileHealthProbeProvider)(value);
    if (!mounted) return;
    if (!probe.ok) {
      setState(() {
        _busy = false;
        _error = probe.error ?? 'Host unreachable.';
      });
      return;
    }
    await ref
        .read(profileStoreProvider)
        .upsert(widget.profile.copyWith(baseUrl: value));
    if (!mounted) return;
    final bool isActive =
        ref.read(activeProfileProvider).id == widget.profile.id;
    if (isActive) {
      // Republish the edited fields (banner, Dio resolvers, thumbnails).
      ref.read(activeProfileProvider.notifier).refreshFromStore();
    } else {
      final SwitchOutcome outcome = await ref
          .read(profileSwitchHandlerProvider)
          .switchTo(widget.profile.id);
      if (!mounted) return;
      if (!outcome.ok) {
        setState(() {
          _busy = false;
          _error = outcome.error ?? 'Host unreachable.';
        });
        return;
      }
    }
    widget.onSaved('Address verified · ${probe.latencyMs} ms');
  }

  @override
  Widget build(BuildContext context) {
    final TextTheme textTheme = Theme.of(context).textTheme;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const LabelCaps(text: 'EDIT ADDRESS'),
        const SizedBox(height: AppSpacing.xs),
        Text(widget.profile.label, style: textTheme.titleSmall),
        const SizedBox(height: AppSpacing.md),
        TextField(
          controller: _urlController,
          enabled: !_busy,
          keyboardType: TextInputType.url,
          autocorrect: false,
          decoration: InputDecoration(
            labelText: 'Base URL',
            hintText: kBaseUrlHint,
            errorText: _error,
          ),
        ),
        const SizedBox(height: AppSpacing.lg),
        Row(
          children: [
            Expanded(
              child: SecondaryButton(
                label: 'Back',
                expanded: true,
                onPressed: _busy ? null : widget.onCancel,
              ),
            ),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: PrimaryButton(
                label: 'Save & test',
                loading: _busy,
                expanded: true,
                onPressed: _busy ? null : _save,
              ),
            ),
          ],
        ),
      ],
    );
  }
}
