import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/platform_repository_impl.dart';
import '../domain/platform.dart';

/// Riverpod: the platform whose data the shell currently shows.
///
/// Seeded with `adobe_stock` (the only available workspace); the hub calls
/// [ActivePlatformNotifier.select] before entering the shell, and every
/// dashboard/gallery/process controller keys off this id (03 §3.5).
final activePlatformIdProvider =
    NotifierProvider<ActivePlatformNotifier, String>(
  ActivePlatformNotifier.new,
);

class ActivePlatformNotifier extends Notifier<String> {
  @override
  String build() => 'adobe_stock';

  /// Switches the active workspace; re-selecting the current id is a no-op.
  void select(String id) {
    if (state == id) {
      return;
    }
    state = id;
  }
}

/// Catalogue for the Platform Hub — `GET /api/platforms/`.
///
/// Async because the picker needs loading/error/offline states (05 §2.3);
/// invalidated by pull-to-refresh and the ErrorView retry.
final platformsProvider = FutureProvider<List<PlatformEntry>>((ref) {
  return ref.watch(platformRepositoryProvider).fetchPlatforms();
});

/// Single platform lookup for the ComingSoon screen —
/// `GET /api/platforms/{platform_id}` (05 §2.10). 404 → [NotFoundException]
/// inside the [AsyncValue.error] slot.
final platformProvider =
    FutureProvider.family<PlatformEntry, String>((ref, platformId) {
  return ref.watch(platformRepositoryProvider).fetchPlatform(platformId);
});
