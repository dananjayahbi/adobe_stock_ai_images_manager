import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show ProviderOrFamily;

import '../../../core/network/auth_cookie_jar.dart';
import '../../../core/network/dio_factory.dart';
import '../../../core/network/session_cookie.dart';
import '../../../core/storage/image_cache.dart';
import '../../dashboard/presentation/dashboard_controller.dart';
import '../../delivery/presentation/delivery_controller.dart';
import '../../gallery/presentation/gallery_controller.dart';
import '../../platforms/presentation/platforms_controller.dart';
import '../../process/presentation/batch_controller.dart';
import '../data/health_api.dart';
import '../data/profile_store.dart';
import '../domain/connection_profile.dart';
import '../domain/settings_repository.dart';

/// Settings feature controller (07 M5): account-form state (GET/PUT
/// `/api/settings`, test/reset) plus the profile-switch seam.
///
/// Test seams, documented up front:
/// * `settingsRepositoryProvider` (domain file) — fake the settings API.
/// * `profileStoreProvider` / `sharedPreferencesProvider` — fake persistence.
/// * `profileHealthProbeProvider` / `profileSwitchTargetsProvider` — script
///   the health gate and observe (or trim) the invalidation set.

/// Reduced-motion master switch (04 §3): `App` folds this into
/// `MediaQuery.disableAnimations` for the whole tree; default off.
final forceReducedMotionProvider = NotifierProvider<ForceReducedMotion, bool>(
  ForceReducedMotion.new,
);

class ForceReducedMotion extends Notifier<bool> {
  @override
  bool build() => false;

  void set(bool value) => state = value;
}

/// Seam for the App-row "Clear image cache" action (04 §5) — tests override
/// with a counting fake instead of touching `flutter_cache_manager`'s disk.
final clearImageCacheProvider = Provider<Future<void> Function()>(
  (ref) => clearImageCache,
);

/// Health probe used by the editor's Test button, the Activate gate and the
/// `/error` retry loop — `GET {baseUrl}/health` with the 3 s budget and a
/// latency reading. Overridable so tests script success/failure per URL.
final profileHealthProbeProvider = Provider<
    Future<HealthProbeResult> Function(String baseUrl)>(
  (ref) => ref.watch(healthApiProvider).probe,
);

/// Providers refetched after a successful profile switch so every screen
/// loads through the new base URL (07 M5: dashboard/gallery/process/delivery
/// controllers + platforms list; settings follows the backend too). Tests
/// override this with a sentinel list to observe invalidation.
final profileSwitchTargetsProvider = Provider<List<ProviderOrFamily>>(
  (ref) => <ProviderOrFamily>[
    dashboardControllerProvider,
    galleryControllerProvider,
    galleryGroupsProvider,
    batchListProvider,
    batchDetailProvider,
    stepCatalogProvider,
    stepProfilesProvider,
    deliveryControllerProvider,
    platformsProvider,
    settingsControllerProvider,
  ],
);

/// Result of a health-gated activation attempt.
class SwitchOutcome {
  const SwitchOutcome.success({this.latencyMs})
      : ok = true,
        error = null;

  const SwitchOutcome.failure(this.error)
      : ok = false,
        latencyMs = null;

  final bool ok;

  /// Round-trip ms of the winning probe (caption: `42 ms`).
  final int? latencyMs;

  /// Failure reason for the inline error; previous profile stays active.
  final String? error;
}

/// The documented profile-switch seam (07 M5, 06 §4.5): health-gate first,
/// persist + publish second, then invalidate feature providers and re-sync
/// the image-loader cookie replay header. Created from a `Ref` so
/// `ref.invalidate` calls land on the same container as the caller.
class ProfileSwitchHandler {
  ProfileSwitchHandler(this._ref);

  final Ref _ref;

  /// Activates [id] **only** after `GET {profile.baseUrl}/health` succeeds.
  /// On probe failure the previous profile stays active and the reason is
  /// returned for inline display.
  Future<SwitchOutcome> switchTo(String id) async {
    final ProfileStore store = _ref.read(profileStoreProvider);
    final List<ConnectionProfile> all = store.profiles();
    int index = -1;
    for (int i = 0; i < all.length; i++) {
      if (all[i].id == id) {
        index = i;
        break;
      }
    }
    if (index < 0) {
      return const SwitchOutcome.failure('Profile not found.');
    }
    if (_ref.read(activeProfileProvider).id == id) {
      return const SwitchOutcome.success(); // Already active — no-op.
    }

    final HealthProbeResult probe =
        await (_ref.read(profileHealthProbeProvider))(all[index].baseUrl);
    if (!probe.ok) {
      return SwitchOutcome.failure(probe.error ?? 'Host unreachable.');
    }

    await _ref.read(activeProfileProvider.notifier).switchTo(id);
    await _syncSessionHeader();
    for (final ProviderOrFamily target
        in _ref.read(profileSwitchTargetsProvider)) {
      _ref.invalidate(target);
    }
    return SwitchOutcome.success(latencyMs: probe.latencyMs);
  }

  /// Delete guard (05 §2.9.1): the active profile can never be removed;
  /// returns the message to toast, or `null` on success. [ProfileStore.remove]
  /// re-seeds the built-ins so the list can never empty.
  Future<String?> deleteProfile(String id) async {
    if (_ref.read(activeProfileProvider).id == id) {
      return "Can't delete the active profile — activate another one first.";
    }
    await _ref.read(profileStoreProvider).remove(id);
    return null;
  }

  /// Republishes the active profile after an edit (label/base URL changed)
  /// so the banner, thumbnails and Dio resolvers pick the new fields up.
  void onActiveProfileEdited() =>
      _ref.read(activeProfileProvider.notifier).refreshFromStore();

  /// The image loaders replay `studio_session` from a process-wide header;
  /// after a switch it must hold the **new** profile's stored pair (06 §4.5 —
  /// per-profile cookies never cross). Best-effort: Dio itself always reads
  /// the jar directly, so a failed sync only affects image headers.
  Future<void> _syncSessionHeader() async {
    try {
      final AuthCookieJar jar = _ref.read(authCookieJarProvider);
      final Uri probeUri =
          Uri.parse(_ref.read(activeProfileProvider).baseUrl);
      final cookies = await jar.loadForRequest(probeUri);
      _ref.read(sessionCookieHeaderProvider.notifier).set(
            cookies.isEmpty ? null : '${cookies.first.name}=${cookies.first.value}',
          );
    } on Object {
      // Best-effort — never fail a completed switch on header sync.
    }
  }
}

final profileSwitchHandlerProvider = Provider<ProfileSwitchHandler>(
  (ref) => ProfileSwitchHandler(ref),
);

/// `/more/account` form state: loads once, applies partial updates, runs the
/// gateway probe and the destructive reset (05 §2.9.2, 02 §8).
final settingsControllerProvider =
    AsyncNotifierProvider<SettingsController, AppSettings>(
  SettingsController.new,
);

/// `GET /api/auth/me` username for the seat note — `null` degrades the
/// line to the generic local-session copy instead of failing the screen.
final accountUsernameProvider = FutureProvider<String?>(
  (ref) => ref.watch(settingsRepositoryProvider).fetchUsername(),
);

class SettingsController extends AsyncNotifier<AppSettings> {
  SettingsRepository get _repository => ref.read(settingsRepositoryProvider);

  @override
  Future<AppSettings> build() => _repository.fetch();

  /// `PUT` a partial patch; blank/masked keys keep the stored key (backend
  /// contract) and the form state lands on the response.
  Future<AppSettings> save(Map<String, dynamic> patch) async {
    final AppSettings updated = await _repository.update(patch);
    state = AsyncData<AppSettings>(updated);
    return updated;
  }

  /// `POST /api/settings/test` against the candidate form values — never
  /// persists; a failed probe is a normal result.
  Future<SettingsTestResult> testCandidate(Map<String, dynamic> candidate) =>
      _repository.test(candidate);

  /// `POST /api/settings/reset` behind a ConfirmDialog (05 §2.9.2).
  Future<AppSettings> reset() async {
    final AppSettings defaults = await _repository.reset();
    state = AsyncData<AppSettings>(defaults);
    return defaults;
  }

  /// Re-reads `GET /api/settings` (pull-to-refresh / profile switch).
  Future<void> reload() async {
    state = await AsyncValue.guard(_repository.fetch);
  }
}
