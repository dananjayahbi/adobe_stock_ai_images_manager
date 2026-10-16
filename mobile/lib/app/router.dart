import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../features/auth/presentation/auth_controller.dart';
import '../features/auth/presentation/login_screen.dart';
import '../features/dashboard/presentation/dashboard_screen.dart';
import '../features/delivery/presentation/delivery_screen.dart';
import '../features/gallery/presentation/gallery_detail_screen.dart';
import '../features/gallery/presentation/gallery_screen.dart';
import '../features/platforms/presentation/coming_soon_screen.dart';
import '../features/platforms/presentation/platform_hub_screen.dart';
import '../features/process/presentation/batch_detail_screen.dart';
import '../features/process/presentation/new_batch_screen.dart';
import '../features/process/presentation/process_screen.dart';
import '../features/settings/presentation/about_screen.dart';
import '../features/settings/presentation/account_screen.dart';
import '../features/settings/presentation/connection_editor_screen.dart';
import '../features/settings/presentation/connections_screen.dart';
import '../features/settings/presentation/diagnostics_screen.dart';
import '../features/settings/presentation/settings_screen.dart';
import 'error_screen.dart';
import 'shell.dart';
import 'splash_screen.dart';

/// Route tree (05 §1.2): `/splash` → `/login` ⇄ `/hub` → shell.
///
/// `/splash`, `/login`, `/hub`, `/coming-soon/:platformId`, the M5 `/more/*`
/// sub-screens (connections, editor, account, about), the full-screen
/// `/error` and the detail/modal views `/gallery/:recordId`, `/process/new`,
/// `/process/:batchId` all live **outside** the [StatefulShellRoute] (no tab
/// bar — 05 §1.2/§2.9/§2.11); the five tabs `/home`, `/gallery`, `/process`,
/// `/delivery`, `/more` sit in indexed-stack branches with their own
/// navigators (back stays in tab). `/process/new` is declared before
/// `/process/:batchId` so the literal `new` never becomes a batch id, and
/// `/more/connections` before `/more/connections/:profileId` likewise. The
/// `/more` tab is the M5 [SettingsScreen]; `/error` carries
/// `?reason=offline|server`.
///
/// **Refresh mechanism.** A single [ValueNotifier] holding the current
/// [AuthStatus] is created inside [routerProvider], kept in sync with
/// [authControllerProvider] through [Ref.listen] (so the [GoRouter] itself is
/// built exactly once), and passed to GoRouter as `refreshListenable`: every
/// status flip — successful login, forced 401 logout, splash probe — re-runs
/// the top-level redirect immediately.
GoRouter createRouter({
  required AuthStatus Function() currentStatus,
  required Listenable refreshListenable,
  String initialLocation = '/splash',
}) {
  return GoRouter(
    initialLocation: initialLocation,
    refreshListenable: refreshListenable,
    redirect: (context, state) => _redirect(currentStatus(), state.uri.path),
    routes: <RouteBase>[
      GoRoute(
        path: '/splash',
        builder: (context, state) => const SplashScreen(),
      ),
      GoRoute(
        path: '/login',
        builder: (context, state) => const LoginScreen(),
      ),
      GoRoute(
        path: '/hub',
        builder: (context, state) => const PlatformHubScreen(),
      ),
      GoRoute(
        path: '/coming-soon/:platformId',
        builder: (context, state) => ComingSoonScreen(
          platformId: state.pathParameters['platformId'] ?? '',
        ),
      ),
      GoRoute(
        path: '/error',
        builder: (context, state) => ErrorScreen(
          reason: state.uri.queryParameters['reason'] ?? 'offline',
        ),
      ),
      GoRoute(
        path: '/diagnostics',
        builder: (context, state) => const DiagnosticsScreen(),
      ),
      GoRoute(
        path: '/more/connections',
        builder: (context, state) => const ConnectionsScreen(),
      ),
      GoRoute(
        path: '/more/connections/:profileId',
        builder: (context, state) => ConnectionEditorScreen(
          profileId: state.pathParameters['profileId'] ?? '',
        ),
      ),
      GoRoute(
        path: '/more/account',
        builder: (context, state) => const AccountScreen(),
      ),
      GoRoute(
        path: '/more/about',
        builder: (context, state) => const AboutScreen(),
      ),
      GoRoute(
        path: '/gallery/:recordId',
        builder: (context, state) => GalleryDetailScreen(
          recordId: state.pathParameters['recordId'] ?? '',
        ),
      ),
      GoRoute(
        path: '/process/new',
        builder: (context, state) => const NewBatchScreen(),
      ),
      GoRoute(
        path: '/process/:batchId',
        builder: (context, state) => BatchDetailScreen(
          batchId: state.pathParameters['batchId'] ?? '',
        ),
      ),
      StatefulShellRoute.indexedStack(
        builder: (context, state, shell) => buildShell(context, state, shell),
        branches: <StatefulShellBranch>[
          StatefulShellBranch(
            routes: <RouteBase>[
              GoRoute(
                path: '/home',
                builder: (context, state) => const DashboardScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: <RouteBase>[
              GoRoute(
                path: '/gallery',
                builder: (context, state) => const GalleryScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: <RouteBase>[
              GoRoute(
                path: '/process',
                builder: (context, state) => const ProcessScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: <RouteBase>[
              GoRoute(
                path: '/delivery',
                builder: (context, state) => const DeliveryScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: <RouteBase>[
              GoRoute(
                path: '/more',
                builder: (context, state) => const SettingsScreen(),
              ),
            ],
          ),
        ],
      ),
    ],
  );
}

/// Auth guard matrix (router tests pin this):
///
/// * `unknown` → stay put — the splash probe owns bootstrap navigation.
/// * `authenticated` → allowed at `/hub`, `/coming-soon/*`, `/error`
///   (offline recovery, 05 §2.11), `/diagnostics` (connection triage) and
///   the shell routes (tabs included —
///   the `_shellRoots` prefix match also covers `/more/*` sub-screens);
///   anything else bounces to `/hub`
///   (covers authenticated-at-`/login`, and auto-advances `/splash`).
/// * `unauthenticated` → anything but `/login` and `/diagnostics` bounces
///   to `/login` (a failed sign-in must still be diagnosable — covers
///   unauthenticated-at-`/hub` and the `/splash` bail-out).
const Set<String> _shellRoots = <String>{
  '/home',
  '/gallery',
  '/process',
  '/delivery',
  '/more',
};

String? _redirect(AuthStatus status, String location) {
  switch (status) {
    case AuthStatus.unknown:
      return null;
    case AuthStatus.authenticated:
      final bool allowed = location == '/hub' ||
          location == '/error' ||
          location == '/diagnostics' ||
          location.startsWith('/coming-soon/') ||
          _shellRoots.contains(location) ||
          _shellRoots.any((String root) => location.startsWith('$root/'));
      return allowed ? null : '/hub';
    case AuthStatus.unauthenticated:
      return location == '/login' || location == '/diagnostics'
          ? null
          : '/login';
  }
}

/// Auth-aware router: watches the controller once to seed the notifier, then
/// only listens — rebuilds of this provider would recreate [GoRouter] and
/// lose navigation state, which is exactly what we avoid.
final routerProvider = Provider<GoRouter>((ref) {
  final ValueNotifier<AuthStatus> status = ValueNotifier<AuthStatus>(
    ref.read(authControllerProvider).value ?? AuthStatus.unknown,
  );
  ref.listen<AsyncValue<AuthStatus>>(authControllerProvider, (_, next) {
    final AuthStatus? nextStatus = next.value;
    if (nextStatus != null && nextStatus != status.value) {
      status.value = nextStatus;
    }
  });
  final GoRouter router = createRouter(
    currentStatus: () => status.value,
    refreshListenable: status,
  );
  ref.onDispose(status.dispose);
  return router;
});

