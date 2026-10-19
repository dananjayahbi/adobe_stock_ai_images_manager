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
import '../features/process/presentation/explorer/explorer_screen.dart';
import '../features/process/presentation/new_batch_screen.dart';
import '../features/process/presentation/process_screen.dart';
import '../features/queue/presentation/queue_screen.dart';
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
/// `/error` and `/delivery` (opened from the More page like the other
/// settings rows — tabs hidden, system back pops) live **outside** the
/// [StatefulShellRoute] (no tab bar — 05 §1.2/§2.9/§2.11); the five
/// tabs `/home`, `/gallery`, `/queue`, `/process`, `/more` sit in
/// indexed-stack branches with their own navigators (back stays in tab).
/// The **Processes** branch (index [kProcessesBranchIndex]) owns the whole
/// `/process` family: the list at its root, then `new`, `pick` (the source
/// explorer) and `:batchId` nested beneath it, so the tab bar stays visible
/// across list → wizard/picker/detail. `/gallery/:recordId` rides
/// **inside** the gallery branch (R4): tabs stay
/// visible while inspecting, Android back pops detail → grid within the
/// branch, and jumping to another tab and returning restores the open
/// detail page + list scroll. Inside the Processes branch, `new` and `pick`
/// are declared before `:batchId` so the literals never become a batch id,
/// and `/more/connections` before `/more/connections/:profileId` likewise.
/// The `/more` tab is the M5 [SettingsScreen]; `/error` carries
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
        path: '/delivery',
        builder: (context, state) => const DeliveryScreen(),
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
                // R4: the detail page lives IN the gallery branch — tabs
                // stay visible, back pops detail → grid within the branch,
                // and tab-hopping restores the open record + scroll.
                routes: <RouteBase>[
                  GoRoute(
                    path: ':recordId',
                    builder: (context, state) => GalleryDetailScreen(
                      recordId: state.pathParameters['recordId'] ?? '',
                    ),
                  ),
                ],
              ),
            ],
          ),
          StatefulShellBranch(
            routes: <RouteBase>[
              // R4: the Queue tab lives at index 2; batches ride their own
              // Processes branch (index 3) beside it.
              GoRoute(
                path: '/queue',
                builder: (context, state) => const QueueScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: <RouteBase>[
              // The Processes tab owns the whole /process family inside
              // the shell (tab bar stays visible — list → wizard/picker/
              // detail all ride this branch). Literal segments are
              // declared before `:batchId` so they never parse as an id.
              GoRoute(
                path: '/process',
                builder: (context, state) => const ProcessScreen(),
                routes: <RouteBase>[
                  GoRoute(
                    path: 'new',
                    builder: (context, state) => const NewBatchScreen(),
                  ),
                  GoRoute(
                    path: 'pick',
                    builder: (context, state) => const ExplorerScreen(),
                  ),
                  GoRoute(
                    path: ':batchId',
                    builder: (context, state) => BatchDetailScreen(
                      batchId: state.pathParameters['batchId'] ?? '',
                    ),
                  ),
                ],
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
///   (offline recovery, 05 §2.11), `/diagnostics` (connection triage),
///   `/delivery` (More → Delivery, outside the shell) and the shell
///   routes (tabs included —
///   the `_shellRoots` prefix match also covers `/more/*` sub-screens and
///   the `/process/*` branch children);
///   anything else bounces to `/hub`
///   (covers authenticated-at-`/login`, and auto-advances `/splash`).
/// * `unauthenticated` → anything but `/login` and `/diagnostics` bounces
///   to `/login` (a failed sign-in must still be diagnosable — covers
///   unauthenticated-at-`/hub` and the `/splash` bail-out).
const Set<String> _shellRoots = <String>{
  '/home',
  '/gallery', // prefix match also covers /gallery/:recordId (in-branch)
  '/queue',
  '/process', // Processes branch: /process, new, pick, :batchId
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
          location == '/delivery' ||
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

