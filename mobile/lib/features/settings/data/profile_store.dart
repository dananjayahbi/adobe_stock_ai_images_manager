import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../core/config/app_config.dart';
import '../domain/connection_profile.dart';

/// Persists connection profiles as JSON in [SharedPreferences]
/// (`profiles_v1` / `active_profile_v1`), per 03 §3.2 and 06 §5.
///
/// Seeds are written on first load; unknown or missing active ids fall
/// back to the first seed so [activeProfile] always returns a usable
/// profile.
class ProfileStore {
  ProfileStore(this._prefs);

  static const String profilesKey = 'profiles_v1';
  static const String activeKey = 'active_profile_v1';

  /// One-time upgrade flag: the legacy first run seeded a localhost profile
  /// (`[local, tunnel]`) which upgrades still carry in `profiles_v1`. It is
  /// purged on the first read after this flag is absent — and the flag is
  /// then set so profiles a developer adds later (Connections → Add) are
  /// never touched.
  static const String migratedLegacyLocalKey = 'migrated_legacy_local_v1';

  /// Built-in seed: the named Cloudflare tunnel (06 §1/§5). The mobile app
  /// is **tunnel-only** — `localhost` from a phone is the phone itself, so
  /// local/loopback profiles are a dev-only affair (add one under
  /// Connections → Add after signing in, e.g. `http://10.0.2.2:8007` on an
  /// emulator or `http://<pc-lan-ip>:8007` on the same Wi-Fi).
  static const ConnectionProfile tunnelSeed = ConnectionProfile(
    id: 'tunnel',
    label: 'Tunnel',
    baseUrl: AppConfig.tunnelBaseUrl,
    hint: 'Named tunnel (studio.hotelgo.lk) — reachable anywhere',
  );

  /// Dev/loopback candidate — intentionally **not** seeded (see
  /// [tunnelSeed]); kept so developers can re-add it from Connections.
  static const ConnectionProfile localSeed = ConnectionProfile(
    id: 'local',
    label: 'Local network',
    baseUrl: AppConfig.devBaseUrl,
    hint: "Android emulator: http://10.0.2.2:8007 — physical device: your PC's LAN IP",
  );

  /// First-run profiles. Tunnel only — one entry, one obvious choice.
  static const List<ConnectionProfile> seeds = [tunnelSeed];

  final SharedPreferences _prefs;

  /// All profiles. Persists and returns the seeds on first load, heals
  /// corrupt or empty stored JSON by re-seeding, and performs the one-time
  /// legacy purge ([migratedLegacyLocalKey]) that drops the old seeded
  /// localhost profile from upgraded installs.
  List<ConnectionProfile> profiles() {
    final bool migrated = _prefs.getBool(migratedLegacyLocalKey) ?? false;
    final String? raw = _prefs.getString(profilesKey);
    if (raw != null) {
      try {
        final List<dynamic> decoded =
            jsonDecode(raw) as List<dynamic>;
        final List<ConnectionProfile> parsed = decoded
            .map(
              (dynamic e) =>
                  ConnectionProfile.fromJson(e as Map<String, dynamic>),
            )
            .toList(growable: false);
        if (parsed.isNotEmpty && parsed.every((p) => p.id.isNotEmpty)) {
          if (!migrated) {
            _prefs.setBool(migratedLegacyLocalKey, true); // fire-and-forget
            final List<ConnectionProfile> cleaned = parsed
                .where((p) => !_isLegacyLocalProfile(p))
                .toList(growable: false);
            if (cleaned.isNotEmpty && cleaned.length != parsed.length) {
              // One-time upgrade: the old `local` seed (or any loopback URL)
              // is useless on a phone and the app is tunnel-only now.
              _writeProfiles(cleaned); // fire-and-forget, like the heal path
              final String? activeId = _prefs.getString(activeKey);
              if (!cleaned.any((p) => p.id == activeId)) {
                _prefs.setString(activeKey, cleaned.first.id);
              }
              return cleaned;
            }
          }
          return parsed;
        }
      } catch (_) {
        // Corrupt JSON or wrong shape — fall through and re-seed.
      }
    }
    if (!migrated) {
      _prefs.setBool(migratedLegacyLocalKey, true); // fire-and-forget
    }
    _writeProfiles(seeds); // idempotent heal; read path stays synchronous
    return List<ConnectionProfile>.of(seeds);
  }

  /// The legacy seed by id, or anything pointing at loopback — neither can
  /// ever be the right target from a phone.
  static bool _isLegacyLocalProfile(ConnectionProfile p) {
    if (p.id == localSeed.id) {
      return true;
    }
    final String host = Uri.tryParse(p.baseUrl)?.host ?? '';
    return host == 'localhost' ||
        host == '::1' ||
        host == '0.0.0.0' ||
        host.startsWith('127.');
  }

  /// Active profile; unknown/missing active id → first seed.
  ConnectionProfile activeProfile() {
    final List<ConnectionProfile> all = profiles();
    final String? activeId = _prefs.getString(activeKey);
    for (final ConnectionProfile profile in all) {
      if (profile.id == activeId) {
        return profile;
      }
    }
    return all.first;
  }

  /// Inserts or replaces the profile with the same [ConnectionProfile.id],
  /// preserving list order.
  Future<void> upsert(ConnectionProfile p) async {
    final List<ConnectionProfile> all = List<ConnectionProfile>.of(
      profiles(),
    );
    final int index = all.indexWhere((e) => e.id == p.id);
    if (index >= 0) {
      all[index] = p;
    } else {
      all.add(p);
    }
    await _writeProfiles(all);
  }

  /// Removes a profile; re-seeds when the list would empty and reassigns
  /// the active profile when it pointed at the removed entry.
  Future<void> remove(String id) async {
    List<ConnectionProfile> remaining =
        profiles().where((p) => p.id != id).toList();
    if (remaining.isEmpty) {
      remaining = List<ConnectionProfile>.of(seeds);
    }
    await _writeProfiles(remaining);
    final String? activeId = _prefs.getString(activeKey);
    final bool activeStillValid =
        remaining.any((p) => p.id == activeId);
    if (!activeStillValid) {
      await _prefs.setString(activeKey, remaining.first.id);
    }
  }

  /// Marks [id] active. Unknown ids are stored as-is; [activeProfile]
  /// falls back to the first seed when they never resolve.
  Future<void> setActive(String id) async {
    await _prefs.setString(activeKey, id);
  }

  Future<void> _writeProfiles(List<ConnectionProfile> all) async {
    final String encoded = jsonEncode(
      all.map((p) => p.toJson()).toList(growable: false),
    );
    await _prefs.setString(profilesKey, encoded);
  }
}

/// Overridden once in bootstrap with the loaded instance.
final sharedPreferencesProvider = Provider<SharedPreferences>(
  (ref) => throw UnimplementedError('override in bootstrap'),
);

final profileStoreProvider = Provider<ProfileStore>(
  (ref) => ProfileStore(ref.watch(sharedPreferencesProvider)),
);

/// Active profile as a **notifying** source of truth (07 M5 profile-switch
/// semantics). The provider name and value type are unchanged from the M0
/// plain `Provider<ConnectionProfile>`, so every existing consumer
/// (`dio_factory` resolvers, banner, thumbnail) compiles as-is — but they now
/// rebuild automatically when [ActiveProfileNotifier.switchTo] flips the
/// active id and every request goes out through the new base URL.
final activeProfileProvider =
    NotifierProvider<ActiveProfileNotifier, ConnectionProfile>(
  ActiveProfileNotifier.new,
);

class ActiveProfileNotifier extends Notifier<ConnectionProfile> {
  @override
  ConnectionProfile build() => ref.watch(profileStoreProvider).activeProfile();

  /// Persists [id] as active, then republishes the resolved profile so every
  /// watcher refetches through the new base URL. Unknown ids fall back to the
  /// first seed exactly like [ProfileStore.activeProfile].
  Future<void> switchTo(String id) async {
    await ref.read(profileStoreProvider).setActive(id);
    state = ref.read(profileStoreProvider).activeProfile();
  }

  /// Re-reads the store after the active profile itself was edited
  /// (label/base-URL change) so watchers see the updated fields.
  void refreshFromStore() {
    final ConnectionProfile resolved =
        ref.read(profileStoreProvider).activeProfile();
    if (state != resolved) {
      state = resolved;
    }
  }
}
