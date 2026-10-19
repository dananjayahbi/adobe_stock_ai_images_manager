import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_flutter/lucide_flutter.dart';

import '../../auth/presentation/auth_controller.dart';
import '../../../app/theme/tokens.dart';
import '../../../core/utils/app_exception.dart';
import '../../../core/utils/ui_message.dart';
import '../../../core/widgets/app_card.dart';
import '../../../core/widgets/error_view.dart';
import '../../../core/widgets/ghost_button.dart';
import '../../../core/widgets/label_caps.dart';
import '../../../core/widgets/primary_button.dart';
import '../../../core/widgets/secondary_button.dart';
import '../../../core/widgets/toast_exception.dart';
import '../domain/settings_repository.dart';
import 'settings_controller.dart';

/// `/more/account` — seat note + metadata-gateway credentials (05 §2.9.2).
///
/// Only what the backend actually exposes (02 §8): `GET/PUT /api/settings`,
/// `POST /api/settings/test|reset`. Keys arrive masked — the eye toggle
/// reveals what the operator is *typing*, never a stored secret. Reset is
/// ConfirmDialog-gated; Sign out tears the local session down.
class AccountScreen extends ConsumerStatefulWidget {
  const AccountScreen({super.key});

  @override
  ConsumerState<AccountScreen> createState() => _AccountScreenState();
}

class _AccountScreenState extends ConsumerState<AccountScreen> {
  final TextEditingController _llmBaseUrl = TextEditingController();
  final TextEditingController _llmModel = TextEditingController();
  final TextEditingController _llmContextWindow = TextEditingController();
  final TextEditingController _llmApiKey = TextEditingController();
  final TextEditingController _braveApiKey = TextEditingController();

  bool _obscureLlmKey = true;
  bool _obscureBraveKey = true;
  bool _braveEnabled = false;
  bool _populated = false;
  bool _saving = false;

  @override
  void dispose() {
    _llmBaseUrl.dispose();
    _llmModel.dispose();
    _llmContextWindow.dispose();
    _llmApiKey.dispose();
    _braveApiKey.dispose();
    super.dispose();
  }

  void _populate(AppSettings settings) {
    _llmBaseUrl.text = settings.llmBaseUrl;
    _llmModel.text = settings.llmModel;
    _llmContextWindow.text =
        settings.llmContextWindow == 0 ? '' : '${settings.llmContextWindow}';
    _braveEnabled = settings.braveSearchEnabled;
    // Keys are never echoed by the backend — the fields start blank with a
    // "keep" hint so a save without typing preserves the stored key.
  }

  Map<String, dynamic> _patchFromForm() {
    final Map<String, dynamic> patch = <String, dynamic>{};
    final String baseUrl = _llmBaseUrl.text.trim();
    if (baseUrl.isNotEmpty) patch['llm_base_url'] = baseUrl;
    final String model = _llmModel.text.trim();
    if (model.isNotEmpty) patch['llm_model'] = model;
    final int? window = int.tryParse(_llmContextWindow.text.trim());
    if (window != null) patch['llm_context_window'] = window;
    final String llmKey = _llmApiKey.text.trim();
    if (llmKey.isNotEmpty) patch['llm_api_key'] = llmKey;
    final String braveKey = _braveApiKey.text.trim();
    if (braveKey.isNotEmpty) patch['brave_search_api_key'] = braveKey;
    patch['brave_search_enabled'] = _braveEnabled;
    return patch;
  }

  String _toastMessage(Object error, String fallback) =>
      error is AppException ? uiMessageFor(error) : fallback;

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      await ref.read(settingsControllerProvider.notifier).save(
            _patchFromForm(),
          );
      _llmApiKey.clear();
      _braveApiKey.clear();
      if (mounted) showAppToast(context, 'Settings saved.', tone: ToastTone.success);
    } on Object catch (e) {
      if (mounted) {
        showAppToast(
          context,
          _toastMessage(e, 'Save failed.'),
          tone: ToastTone.error,
        );
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _testGateway() async {
    try {
      final SettingsTestResult result = await ref
          .read(settingsControllerProvider.notifier)
          .testCandidate(_patchFromForm());
      if (!mounted) {
        return;
      }
      showAppToast(
        context,
        result.ok
            ? 'Gateway answered${result.model == null ? '' : ' · ${result.model}'}.'
            : result.error ?? 'Gateway probe failed.',
        tone: result.ok ? ToastTone.success : ToastTone.error,
      );
    } on Object catch (e) {
      if (mounted) {
        showAppToast(
          context,
          _toastMessage(e, 'Gateway probe failed.'),
          tone: ToastTone.error,
        );
      }
    }
  }

  Future<void> _reset() async {
    final bool? confirmed = await showDialog<bool>(
      context: context,
      builder: (BuildContext dialogContext) => AlertDialog(
        title: const Text('Reset settings?'),
        content: const Text(
          'Every override falls back to the server .env defaults. '
          'Stored keys are dropped.',
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('Reset'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    try {
      final AppSettings defaults =
          await ref.read(settingsControllerProvider.notifier).reset();
      _populate(defaults);
      _llmApiKey.clear();
      _braveApiKey.clear();
      if (mounted) showAppToast(context, 'Settings reset to defaults.', tone: ToastTone.success);
    } on Object catch (e) {
      if (mounted) {
        showAppToast(
          context,
          _toastMessage(e, 'Reset failed.'),
          tone: ToastTone.error,
        );
      }
    }
  }

  InputDecoration _obscureDecoration({
    required String label,
    required String hint,
    required bool obscured,
    required VoidCallback toggle,
  }) =>
      InputDecoration(
        labelText: label,
        hintText: hint,
        suffixIcon: IconButton(
          tooltip: obscured ? 'Show API key' : 'Hide API key',
          constraints: const BoxConstraints(minWidth: 44, minHeight: 44),
          onPressed: toggle,
          icon: Icon(
            obscured ? Icons.visibility_outlined : Icons.visibility_off_outlined,
            semanticLabel: obscured ? 'Show API key' : 'Hide API key',
          ),
        ),
      );

  @override
  Widget build(BuildContext context) {
    final AsyncValue<AppSettings> settingsAsync =
        ref.watch(settingsControllerProvider);
    final AsyncValue<String?> user = ref.watch(accountUsernameProvider);
    final TextTheme textTheme = Theme.of(context).textTheme;

    settingsAsync.whenData((AppSettings settings) {
      if (!_populated) {
        _populated = true;
        _populate(settings);
      }
    });

    return Scaffold(
      appBar: AppBar(title: const Text('Account')),
      body: SafeArea(
        child: settingsAsync.when(
          loading: () =>
              const Center(child: CircularProgressIndicator()),
          error: (Object error, StackTrace _) => ErrorView(
            message: _toastMessage(
              error,
              'Something went wrong.',
            ),
            onRetry: () =>
                ref.read(settingsControllerProvider.notifier).reload(),
          ),
          data: (AppSettings settings) => ListView(
            padding: const EdgeInsets.all(AppSpacing.lg),
            children: <Widget>[
              AppCard(
                child: Column(
                  children: <Widget>[
                    Row(
                      children: <Widget>[
                        const Icon(
                          LucideIcons.userRound,
                          size: 20,
                          color: AppColors.brass400,
                        ),
                        const SizedBox(width: AppSpacing.md),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: <Widget>[
                              Text(
                                user.maybeWhen<String>(
                                  data: (String? name) =>
                                      name ?? 'Local session',
                                  orElse: () => 'Local session',
                                ),
                                style: textTheme.bodyMedium
                                    ?.copyWith(color: AppColors.ink800),
                              ),
                              const SizedBox(height: 2),
                              Text(
                                'Local session · one seat',
                                style: textTheme.bodySmall
                                    ?.copyWith(color: AppColors.ink400),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: AppSpacing.sm),
                    GhostButton(
                      label: 'Sign out',
                      expanded: true,
                      onPressed: () => ref
                          .read(authControllerProvider.notifier)
                          .logout(),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: AppSpacing.xl),
              const LabelCaps(text: 'Metadata gateway'),
              const SizedBox(height: AppSpacing.sm),
              AppCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: <Widget>[
                    Text(
                      settings.llmApiKeySet
                          ? 'LLM key saved (${settings.llmApiKeyMasked}) — '
                              'leave blank to keep it.'
                          : 'No LLM key stored yet.',
                      style: textTheme.bodySmall
                          ?.copyWith(color: AppColors.ink400),
                    ),
                    const SizedBox(height: AppSpacing.md),
                    TextField(
                      controller: _llmBaseUrl,
                      keyboardType: TextInputType.url,
                      decoration: InputDecoration(
                        labelText: 'LLM base URL',
                        hintText: settings.effectiveBaseUrl,
                      ),
                    ),
                    const SizedBox(height: AppSpacing.md),
                    TextField(
                      controller: _llmModel,
                      decoration: InputDecoration(
                        labelText: 'Model',
                        hintText: settings.effectiveModel,
                      ),
                    ),
                    const SizedBox(height: AppSpacing.md),
                    TextField(
                      controller: _llmContextWindow,
                      keyboardType: TextInputType.number,
                      decoration: const InputDecoration(
                        labelText: 'Context window',
                        hintText: 'tokens',
                      ),
                    ),
                    const SizedBox(height: AppSpacing.md),
                    TextField(
                      controller: _llmApiKey,
                      obscureText: _obscureLlmKey,
                      decoration: _obscureDecoration(
                        label: 'LLM API key',
                        hint: settings.llmApiKeySet ? '••••••••' : 'not set',
                        obscured: _obscureLlmKey,
                        toggle: () => setState(
                          () => _obscureLlmKey = !_obscureLlmKey,
                        ),
                      ),
                    ),
                    const SizedBox(height: AppSpacing.md),
                    TextField(
                      controller: _braveApiKey,
                      obscureText: _obscureBraveKey,
                      decoration: _obscureDecoration(
                        label: 'Brave search key',
                        hint: settings.braveSearchApiKeySet
                            ? settings.braveSearchApiKeyMasked
                            : 'not set',
                        obscured: _obscureBraveKey,
                        toggle: () => setState(
                          () => _obscureBraveKey = !_obscureBraveKey,
                        ),
                      ),
                    ),
                    Row(
                      children: <Widget>[
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: <Widget>[
                              Text(
                                'Brave web search',
                                style: textTheme.bodyMedium
                                    ?.copyWith(color: AppColors.ink800),
                              ),
                              const SizedBox(height: 2),
                              Text(
                                settings.effectiveUsesBrave
                                    ? 'Active with the stored key'
                                    : 'Off or missing key',
                                style: textTheme.bodySmall
                                    ?.copyWith(color: AppColors.ink400),
                              ),
                            ],
                          ),
                        ),
                        Switch(
                          value: _braveEnabled,
                          onChanged: (bool value) =>
                              setState(() => _braveEnabled = value),
                        ),
                      ],
                    ),
                    const SizedBox(height: AppSpacing.sm),
                    PrimaryButton(
                      label: 'Save',
                      loading: _saving,
                      expanded: true,
                      onPressed: _saving ? null : _save,
                    ),
                    const SizedBox(height: AppSpacing.sm),
                    SecondaryButton(
                      label: 'Test gateway',
                      expanded: true,
                      onPressed: _saving ? null : _testGateway,
                    ),
                    const SizedBox(height: AppSpacing.sm),
                    SecondaryButton(
                      label: 'Reset to defaults',
                      expanded: true,
                      onPressed: _saving ? null : _reset,
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
