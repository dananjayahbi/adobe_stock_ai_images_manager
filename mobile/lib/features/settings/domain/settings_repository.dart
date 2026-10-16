import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/dio_factory.dart';
import '../data/settings_repository_impl.dart';

/// `GET/PUT /api/settings`, `POST /api/settings/test|reset` (02 §8, 07 M5).
///
/// Repository wired to the shared Dio client — cookie flows ride for free
/// (the settings endpoints require the `studio_session` cookie). Widget
/// tests override this provider to fake the backend without touching Dio.
final settingsRepositoryProvider = Provider<SettingsRepository>(
  (ref) => SettingsRepositoryImpl(ref.watch(dioProvider)),
);

/// Operator-editable gateway settings (LLM + search credentials).
///
/// Field names mirror the backend `SettingsResponse` verbatim (read from
/// `backend/schemas.py` — backend truth wins); keys arrive **masked**
/// (`llm_api_key_masked`) and are never returned raw.
class AppSettings {
  const AppSettings({
    required this.llmBaseUrl,
    required this.llmModel,
    required this.llmApiKeyMasked,
    required this.llmApiKeySet,
    required this.llmContextWindow,
    required this.braveSearchEnabled,
    required this.braveSearchApiKeyMasked,
    required this.braveSearchApiKeySet,
    required this.effectiveBaseUrl,
    required this.effectiveModel,
    required this.effectiveUsesBrave,
  });

  factory AppSettings.fromJson(Map<String, dynamic> json) => AppSettings(
        llmBaseUrl: json['llm_base_url'] as String? ?? '',
        llmModel: json['llm_model'] as String? ?? '',
        llmApiKeyMasked: json['llm_api_key_masked'] as String? ?? '',
        llmApiKeySet: json['llm_api_key_set'] as bool? ?? false,
        llmContextWindow: json['llm_context_window'] as int? ?? 0,
        braveSearchEnabled: json['brave_search_enabled'] as bool? ?? false,
        braveSearchApiKeyMasked:
            json['brave_search_api_key_masked'] as String? ?? '',
        braveSearchApiKeySet: json['brave_search_api_key_set'] as bool? ?? false,
        effectiveBaseUrl: json['effective_base_url'] as String? ?? '',
        effectiveModel: json['effective_model'] as String? ?? '',
        effectiveUsesBrave: json['effective_uses_brave'] as bool? ?? false,
      );

  /// Stored LLM endpoint (empty → environment default).
  final String llmBaseUrl;

  /// Stored model name (empty → environment default).
  final String llmModel;

  /// Masked LLM key as handed back by GET (`********jkdf`).
  final String llmApiKeyMasked;

  /// Whether a usable LLM key is stored.
  final bool llmApiKeySet;

  /// Stored context window (bounded server-side).
  final int llmContextWindow;

  /// Whether the Brave search provider is enabled.
  final bool braveSearchEnabled;

  /// Masked Brave key (`brave:********9OAG`).
  final String braveSearchApiKeyMasked;

  /// Whether a usable Brave key is stored.
  final bool braveSearchApiKeySet;

  /// What a request would use right now (stored ⊕ environment).
  final String effectiveBaseUrl;

  /// Model a request would use right now.
  final String effectiveModel;

  /// Whether the Brave provider actually runs (enabled **and** keyed).
  final bool effectiveUsesBrave;
}

/// Outcome of `POST /api/settings/test` — a failed probe is a normal
/// result, not an HTTP error (rendered inline / toasted).
class SettingsTestResult {
  const SettingsTestResult({required this.ok, this.model, this.error});

  factory SettingsTestResult.fromJson(Map<String, dynamic> json) =>
      SettingsTestResult(
        ok: json['ok'] as bool? ?? false,
        model: json['model'] as String?,
        error: json['error'] as String?,
      );

  final bool ok;
  final String? model;
  final String? error;
}

/// Settings port consumed by presentation (03 layering). Implementations
/// never leak [DioException] — errors surface as `AppException`s.
abstract interface class SettingsRepository {
  /// `GET /api/settings` — masked keys, effective values, bounds.
  Future<AppSettings> fetch();

  /// `PUT /api/settings` — partial update; omitted fields untouched,
  /// blank/masked keys mean "keep the stored key" (backend contract).
  Future<AppSettings> update(Map<String, dynamic> patch);

  /// `POST /api/settings/test` — probes a copy of the config (never pins).
  Future<SettingsTestResult> test([Map<String, dynamic>? candidate]);

  /// `POST /api/settings/reset` — drops overrides back to `.env` defaults.
  Future<AppSettings> reset();

  /// `GET /api/auth/me` — the session's username for the seat note on
  /// `/more/account`. Lives here (not in the auth feature) so the settings
  /// screens own their data end-to-end without widening the auth port;
  /// `null` when no session answers.
  Future<String?> fetchUsername();
}
