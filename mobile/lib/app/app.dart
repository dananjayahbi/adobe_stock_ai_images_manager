import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../features/auth/presentation/auth_controller.dart';
import '../features/settings/data/health_api.dart';
import '../features/settings/presentation/settings_controller.dart';
import '../core/utils/app_exception.dart';
import 'lifecycle_observer.dart';
import 'router.dart';
import 'theme/theme.dart';

/// App root: dark theme + auth-aware router (M1 has no shell — M2 adds
/// `StatefulShellRoute` behind the same [routerProvider]).
class App extends ConsumerWidget {
  const App({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Resume hook (03 §4): best-effort health ping, then session revalidation.
    // refresh() never throws and keeps the previous status offline.
    AppLifecycleHooks.onResume = () async {
      try {
        await ref.read(healthApiProvider).sessionAlive();
      } on AppException {
        // Ping is advisory — the refresh below decides the session state.
      }
      await ref.read(authControllerProvider.notifier).refresh();
    };

    // Reduced motion (04 §3): the App-row switch folds into the media query
    // so every `disableAnimations` consumer (stamps, toasts, LiveDot) freezes.
    final bool forceReducedMotion = ref.watch(forceReducedMotionProvider);
    final MediaQueryData base = MediaQuery.of(context);

    return MediaQuery(
      data: base.copyWith(
        disableAnimations:
            base.disableAnimations || forceReducedMotion,
      ),
      child: MaterialApp.router(
        title: 'AI Stock Studio',
        debugShowCheckedModeBanner: false,
        theme: buildAppTheme(),
        themeMode: ThemeMode.dark,
        routerConfig: ref.watch(routerProvider),
      ),
    );
  }
}
