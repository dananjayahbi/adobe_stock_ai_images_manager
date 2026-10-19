import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../features/auth/presentation/auth_controller.dart';
import '../features/settings/data/health_api.dart';
import '../features/settings/data/profile_auto_fallback.dart';
import '../core/network/dio_factory.dart';
import '../core/widgets/label_caps.dart';
import '../core/widgets/stamp_in.dart';
import 'theme/tokens.dart';

/// The one boot job splash runs before deciding Login vs Hub — injected so
/// widget tests can hang it (or resolve it) without touching the network.
class SplashDependencies {
  const SplashDependencies({required this.probe, required this.cap});

  /// Session + health revalidation; failures are swallowed by the default
  /// implementation (05 §2.1: degraded boot still proceeds).
  final Future<void> Function() probe;

  /// Hard cap before the screen navigates regardless (05 §2.1 ~2.5 s).
  final Duration cap;
}

const Duration kSplashCap = Duration(milliseconds: 2500);

/// Default [SplashDependencies]: fire-and-forget `GET /api/platforms/`
/// (02 §2 gotcha — trailing slash is mandatory), health ping and
/// `authController.refresh()` in parallel.
final splashDependenciesProvider = Provider<SplashDependencies>((ref) {
  return SplashDependencies(cap: kSplashCap, probe: () async {
    // Reachability fallback first: a fresh phone install defaults to the
    // `localhost` profile (the device itself) — activate a profile that
    // actually answers before anything below fires, so session/platforms
    // traffic lands on the resolved host.
    await _swallow(ref.read(profileAutoFallbackProvider)());
    unawaited(
      ref
          .read(dioProvider)
          .get('/api/platforms/')
          .then<void>((_) {}, onError: (Object _, StackTrace _) {}),
    );
    await Future.wait<void>(<Future<void>>[
      _swallow(ref.read(healthApiProvider).sessionAlive()),
      _swallow(ref.read(authControllerProvider.notifier).refresh()),
    ]);
  });
});

Future<void> _swallow(Future<Object?> future) async {
  try {
    await future;
  } catch (_) {
    // Best-effort bootstrap — splash routes on the final auth status anyway.
  }
}

/// `/splash` (05 §2.1): stamp-in wordmark + progress while the probe runs;
/// navigates as soon as the probe settles or the [SplashDependencies.cap]
/// fires, whichever comes first. Never returned to (router redirect guards).
class SplashScreen extends ConsumerStatefulWidget {
  const SplashScreen({super.key, this.dependencies});

  /// Test seam — defaults to [splashDependenciesProvider].
  final SplashDependencies? dependencies;

  @override
  ConsumerState<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends ConsumerState<SplashScreen> {
  late final SplashDependencies _deps;
  Timer? _capTimer;
  bool _departed = false;

  @override
  void initState() {
    super.initState();
    _deps = widget.dependencies ?? ref.read(splashDependenciesProvider);
    _capTimer = Timer(_deps.cap, _depart);
    unawaited(_probe());
  }

  Future<void> _probe() async {
    try {
      await _deps.probe();
    } catch (_) {
      // Failures fall through: unknown status routes to /login below.
    }
    _depart();
  }

  void _depart() {
    if (_departed) return;
    _departed = true;
    if (!mounted) return;
    final AuthStatus status =
        ref.read(authControllerProvider).value ?? AuthStatus.unauthenticated;
    context.go(status == AuthStatus.authenticated ? '/hub' : '/login');
  }

  @override
  void dispose() {
    _capTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final TextTheme textTheme = Theme.of(context).textTheme;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              StampIn(
                child: Text(
                  'AI STOCK STUDIO',
                  textAlign: TextAlign.center,
                  style: textTheme.displaySmall,
                ),
              ),
              const SizedBox(height: AppSpacing.lg),
              const LabelCaps(text: 'Opening the studio…'),
              const SizedBox(height: AppSpacing.xl),
              const SizedBox(
                width: 120,
                child: LinearProgressIndicator(
                  minHeight: 2,
                  color: AppColors.brass400,
                  backgroundColor: AppColors.parchment300,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
