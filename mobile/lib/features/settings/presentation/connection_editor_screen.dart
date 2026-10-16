import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:lucide_flutter/lucide_flutter.dart';

import '../../../app/theme/tokens.dart';
import '../../../core/widgets/app_card.dart';
import '../../../core/widgets/label_caps.dart';
import '../../../core/widgets/primary_button.dart';
import '../../../core/widgets/secondary_button.dart';
import '../../../core/widgets/toast_exception.dart';
import '../data/health_api.dart';
import '../data/profile_store.dart';
import '../domain/connection_profile.dart';
import 'settings_controller.dart';

/// Field hints per 06 §5: LAN IP, named tunnel host, Android-emulator alias.
const String kBaseUrlHint = 'studio.hotelgo.lk · 192.168.x.x · 10.0.2.2';

/// URL rule: scheme must be http/https and a host must be present — the
/// exact message the tests pin; `null` means valid.
String? validateBaseUrl(String value) {
  final String trimmed = value.trim();
  if (trimmed.isEmpty) {
    return 'Required';
  }
  final Uri? uri = Uri.tryParse(trimmed);
  if (uri == null ||
      !(uri.isScheme('http') || uri.isScheme('https')) ||
      uri.host.isEmpty) {
    return 'Enter a full http:// or https:// URL.';
  }
  return null;
}

/// `/more/connections/:profileId` — label + base URL form with inline
/// validation, Save (upsert), Test (probe → `42 ms` / failure reason) and
/// Activate (health-gated; failure keeps the previous profile, 06 §5).
/// The sentinel id `new` opens a blank draft.
class ConnectionEditorScreen extends ConsumerStatefulWidget {
  const ConnectionEditorScreen({super.key, required this.profileId});

  final String profileId;

  @override
  ConsumerState<ConnectionEditorScreen> createState() =>
      _ConnectionEditorScreenState();
}

class _ConnectionEditorScreenState
    extends ConsumerState<ConnectionEditorScreen> {
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  final TextEditingController _label = TextEditingController();
  final TextEditingController _baseUrl = TextEditingController();

  bool _isNew = false;
  ConnectionProfile? _existing;
  bool _saving = false;
  bool _probing = false;
  bool _activating = false;
  HealthProbeResult? _probeResult;
  String? _activateError;

  @override
  void initState() {
    super.initState();
    _isNew = widget.profileId == 'new';
    if (!_isNew) {
      for (final ConnectionProfile p
          in ref.read(profileStoreProvider).profiles()) {
        if (p.id == widget.profileId) {
          _existing = p;
          break;
        }
      }
      // Unknown id → blank draft that upserts under that id.
      _isNew = _existing == null;
      _label.text = _existing?.label ?? '';
      _baseUrl.text = _existing?.baseUrl ?? '';
    }
  }

  @override
  void dispose() {
    _label.dispose();
    _baseUrl.dispose();
    super.dispose();
  }

  String _slugify(String label) {
    final String slug = label
        .toLowerCase()
        .replaceAll(RegExp(r'[^a-z0-9]+'), '-')
        .replaceAll(RegExp(r'^-+|-+$'), '');
    if (slug.isEmpty) {
      return 'profile';
    }
    final List<ConnectionProfile> all =
        ref.read(profileStoreProvider).profiles();
    String candidate = slug;
    int n = 2;
    while (all.any((ConnectionProfile p) => p.id == candidate)) {
      candidate = '$slug-$n';
      n++;
    }
    return candidate;
  }

  Future<void> _save() async {
    if (!(_formKey.currentState?.validate() ?? false)) {
      return;
    }
    setState(() {
      _saving = true;
      _activateError = null;
    });
    final String id = _existing?.id ??
        (widget.profileId == 'new'
            ? _slugify(_label.text.trim())
            : widget.profileId);
    final ConnectionProfile saved = ConnectionProfile(
      id: id,
      label: _label.text.trim(),
      baseUrl: _baseUrl.text.trim(),
      lastStatus: _existing?.lastStatus,
      lastCheckedAt: _existing?.lastCheckedAt,
      hint: _existing?.hint,
    );
    await ref.read(profileStoreProvider).upsert(saved);
    final bool wasActive = ref.read(activeProfileProvider).id == id;
    if (wasActive) {
      // Base URL / label of the active profile changed — republish so the
      // banner, thumbnails and Dio resolvers pick it up immediately.
      ref.read(profileSwitchHandlerProvider).onActiveProfileEdited();
    }
    if (!mounted) {
      return;
    }
    setState(() {
      _existing = saved;
      _isNew = false;
      _saving = false;
    });
    showAppToast(context, 'Profile saved.', tone: ToastTone.success);
  }

  Future<void> _test() async {
    if (!(_formKey.currentState?.validate() ?? false)) {
      return;
    }
    setState(() {
      _probing = true;
      _probeResult = null;
    });
    final HealthProbeResult result = await ref
        .read(profileHealthProbeProvider)(_baseUrl.text.trim());
    if (!mounted) {
      return;
    }
    setState(() {
      _probeResult = result;
      _probing = false;
    });
  }

  Future<void> _activate() async {
    final String? urlError = validateBaseUrl(_baseUrl.text);
    if (urlError != null) {
      _formKey.currentState?.validate();
      return;
    }
    setState(() {
      _activating = true;
      _activateError = null;
    });
    final SwitchOutcome outcome = await ref
        .read(profileSwitchHandlerProvider)
        .switchTo(_existing?.id ?? widget.profileId);
    if (!mounted) {
      return;
    }
    setState(() => _activating = false);
    if (outcome.ok) {
      if (context.mounted) {
        showAppToast(
          context,
          outcome.latencyMs == null
              ? 'Already the active profile.'
              : 'Switched · ${outcome.latencyMs} ms',
          tone: ToastTone.success,
        );
        context.pop();
      }
    } else {
      setState(
        () => _activateError = outcome.error ?? 'Host unreachable.',
      );
    }
  }

  Widget _probeCaption() {
    final HealthProbeResult? result = _probeResult;
    if (result == null) {
      return const SizedBox.shrink();
    }
    final Color color = result.ok ? AppColors.olive400 : AppColors.rust400;
    final String text = result.ok
        ? 'OK · ${result.latencyMs} ms'
        : result.error ?? 'Host unreachable.';
    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.sm),
      child: Row(
        children: <Widget>[
          Icon(
            result.ok ? LucideIcons.circleCheck : LucideIcons.circleX,
            size: 16,
            color: color,
          ),
          const SizedBox(width: AppSpacing.xs),
          Flexible(
            child: Text(
              text,
              style: Theme.of(context)
                  .textTheme
                  .bodySmall
                  ?.copyWith(color: color),
            ),
          ),
        ],
      ),
    );
  }

  Widget _activateErrorCaption() {
    final String? error = _activateError;
    if (error == null) {
      return const SizedBox.shrink();
    }
    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.sm),
      child: Row(
        children: <Widget>[
          const Icon(
            LucideIcons.circleAlert,
            size: 16,
            color: AppColors.rust400,
          ),
          const SizedBox(width: AppSpacing.xs),
          Flexible(
            child: Text(
              'Could not switch — $error The previous profile stays active.',
              style: Theme.of(context)
                  .textTheme
                  .bodySmall
                  ?.copyWith(color: AppColors.rust400),
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final TextTheme textTheme = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(
        title: Text(_isNew && _existing == null
            ? 'Add profile'
            : _existing?.label ?? 'Edit profile'),
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(AppSpacing.lg),
          children: <Widget>[
            AppCard(
              child: Form(
                key: _formKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: <Widget>[
                    const LabelCaps(text: 'Name'),
                    const SizedBox(height: AppSpacing.xs),
                    TextFormField(
                      controller: _label,
                      enabled: !_saving,
                      textInputAction: TextInputAction.next,
                      decoration: const InputDecoration(
                        labelText: 'Label',
                        hintText: 'Studio tunnel · Backup · Hotspot',
                      ),
                      validator: (String? value) =>
                          value == null || value.trim().isEmpty
                              ? 'Required'
                              : null,
                    ),
                    const SizedBox(height: AppSpacing.lg),
                    const LabelCaps(text: 'Base URL'),
                    const SizedBox(height: AppSpacing.xs),
                    TextFormField(
                      controller: _baseUrl,
                      enabled: !_saving,
                      keyboardType: TextInputType.url,
                      autofillHints: const [AutofillHints.url],
                      decoration: InputDecoration(
                        labelText: 'Base URL',
                        hintText: kBaseUrlHint,
                        helperText: _existing?.hint,
                      ),
                    validator: (String? value) =>
                        validateBaseUrl(value ?? ''),
                    ),
                    const SizedBox(height: AppSpacing.lg),
                    Row(
                      children: <Widget>[
                        Expanded(
                          child: SecondaryButton(
                            label: 'Test',
                            loading: _probing,
                            onPressed:
                                _probing || _saving ? null : _test,
                          ),
                        ),
                        const SizedBox(width: AppSpacing.md),
                        Expanded(
                          child: PrimaryButton(
                            label: 'Save',
                            loading: _saving,
                            onPressed:
                                _saving ? null : _save,
                          ),
                        ),
                      ],
                    ),
                    _probeCaption(),
                  ],
                ),
              ),
            ),
            if (_existing != null) ...<Widget>[
              const SizedBox(height: AppSpacing.xl),
              const LabelCaps(text: 'Activation'),
              const SizedBox(height: AppSpacing.sm),
              AppCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: <Widget>[
                    Text(
                      'Switching runs a health check first — on failure the '
                      'previous profile stays active (06 §5).',
                      style: textTheme.bodySmall
                          ?.copyWith(color: AppColors.ink400, height: 1.5),
                    ),
                    const SizedBox(height: AppSpacing.md),
                    PrimaryButton(
                      label: 'Activate',
                      loading: _activating,
                      expanded: true,
                      onPressed: _activating ? null : _activate,
                    ),
                    _activateErrorCaption(),
                  ],
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
