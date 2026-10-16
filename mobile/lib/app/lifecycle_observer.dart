import 'dart:async';

import 'package:flutter/widgets.dart';

/// Static hooks the running app wires in (03 §4).
///
/// A registry instead of constructor injection because `bootstrap()`
/// constructs the observer before any `WidgetRef`/`ProviderContainer` exists
/// and its registration mechanism (`WidgetsBinding.addObserver`) must stay
/// intact (M5 owns `lifecycle_observer.dart` only, not `app.dart`).
abstract final class AppLifecycleHooks {
  /// Session revalidation on resume: `GET /health` + `GET /api/auth/me`.
  /// Assigned by `App.build` (`healthApi.sessionAlive()` then
  /// `authControllerProvider.refresh()`); `null` before the first build (and
  /// in tests that never pump the app) makes the session step a no-op.
  static Future<void> Function()? onResume;

  /// Feature controllers (dashboard/gallery/process/delivery) invalidated on
  /// resume. Keyed so each tab root re-registers on rebuild with a fresh
  /// container-based closure; the container is app-scoped, so the stored
  /// callback stays safe long after any widget unmounts.
  static final Map<String, VoidCallback> _featureInvalidators =
      <String, VoidCallback>{};

  /// Registers (or replaces, when [key] is seen again on rebuild) the
  /// resume invalidator for one feature root.
  static void registerFeatureInvalidator(String key, VoidCallback invalidate) {
    _featureInvalidators[key] = invalidate;
  }

  /// Runs every registered feature invalidator — called by the observer
  /// after the session hook and directly by tests.
  static void invalidateFeatures() {
    for (final VoidCallback invalidate
        in _featureInvalidators.values.toList(growable: false)) {
      invalidate();
    }
  }

  /// Test hook: drops the session callback and every registered invalidator.
  @visibleForTesting
  static void reset() {
    onResume = null;
    _featureInvalidators.clear();
  }
}

/// App-lifecycle observer (NOT Riverpod's `ProviderObserver`) per 03 §4:
///
/// * `resumed` → await [AppLifecycleHooks.onResume] (health ping + session
///   revalidation), then [AppLifecycleHooks.invalidateFeatures] so the four
///   feature controllers refetch against the revalidated session. The
///   invalidation runs in a `finally` and the hook is best-effort — neither
///   can skip the other.
/// * `paused` → mark inactive (observable via [isInactive]); SSE sockets
///   already close in their widgets' `dispose` (mobile OSes throttle
///   background sockets), so nothing else needs cancelling here.
class AppLifecycleObserver extends WidgetsBindingObserver {
  AppLifecycleObserver();

  AppLifecycleState? _lastState;

  /// Last observed lifecycle state; `null` until the first event.
  AppLifecycleState? get lastState => _lastState;

  /// True from any non-`resumed` state (paused, hidden, transiently
  /// inactive) until the next resume.
  bool get isInactive =>
      _lastState != null && _lastState != AppLifecycleState.resumed;

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _lastState = state;
    if (state != AppLifecycleState.resumed) return;
    unawaited(_onResume());
  }

  Future<void> _onResume() async {
    try {
      final Future<void> Function()? hook = AppLifecycleHooks.onResume;
      if (hook != null) {
        await hook();
      }
    } on Object {
      // Session revalidation is advisory (03 §4) — an unexpected failure
      // must not swallow the provider refresh below.
    } finally {
      AppLifecycleHooks.invalidateFeatures();
    }
  }
}
