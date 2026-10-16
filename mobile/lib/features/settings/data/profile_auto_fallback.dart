import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../domain/connection_profile.dart';
import 'health_api.dart';
import 'profile_store.dart';

/// Splash-time reachability fallback: when the active profile's `/health`
/// fails, probe the remaining profiles in stored order and activate the
/// first one that answers (remote-first boot — a fresh install defaults to
/// `localhost`, which is the *device itself* on a phone).
///
/// Runs **before** the session/platforms probes in the default splash probe
/// so every follow-up request goes to the resolved host. Deliberately a fast
/// persist in `settings/data`: nothing is cached pre-login, so the full
/// health-gated, invalidating switch (`profileSwitchHandlerProvider`) is only
/// needed by the interactive switchers, not by boot.
final profileAutoFallbackProvider = Provider<Future<String?> Function()>(
  (ref) => () => _ensureReachable(ref),
);

/// Probe seam for [profileAutoFallbackProvider] — tests script per-URL
/// outcomes here (mirrors `profileHealthProbeProvider` in settings).
final profileFallbackProbeProvider = Provider<
    Future<HealthProbeResult> Function(String baseUrl)>(
  (ref) => ref.watch(healthApiProvider).probe,
);

/// Returns the id of the profile switched to, or `null` when the active
/// profile is already reachable (or no candidate answers).
Future<String?> _ensureReachable(Ref ref) async {
  final ConnectionProfile active = ref.read(activeProfileProvider);
  final HealthProbeResult probe =
      await ref.read(profileFallbackProbeProvider)(active.baseUrl);
  if (probe.ok) {
    return null;
  }
  for (final ConnectionProfile candidate
      in ref.read(profileStoreProvider).profiles()) {
    if (candidate.id == active.id) {
      continue;
    }
    final HealthProbeResult result =
        await ref.read(profileFallbackProbeProvider)(candidate.baseUrl);
    if (result.ok) {
      await ref.read(activeProfileProvider.notifier).switchTo(candidate.id);
      return candidate.id;
    }
  }
  return null;
}
