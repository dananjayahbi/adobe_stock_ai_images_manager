import 'package:flutter/widgets.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../core/network/dns_fallback.dart';
import 'lifecycle_observer.dart';

/// Whatever `main()` needs before handing control to the widget tree (03 §4).
class BootstrapHandles {
  const BootstrapHandles({required this.prefs});

  final SharedPreferences prefs;
}

/// Async pre-run wiring: binding + persistent key-value store. Kept tiny on
/// purpose — providers are assembled inside `ProviderScope` overrides.
Future<BootstrapHandles> bootstrap() async {
  WidgetsFlutterBinding.ensureInitialized();
  // DNS fallback relay + HttpOverrides (native no-op on web) — started
  // before any provider or request can resolve a host (07 §2).
  await enableDnsFallback();
  final SharedPreferences prefs = await SharedPreferences.getInstance();
  // App-lifecycle observer: resume hook is attached later by `App.build`.
  WidgetsBinding.instance.addObserver(AppLifecycleObserver());
  return BootstrapHandles(prefs: prefs);
}
