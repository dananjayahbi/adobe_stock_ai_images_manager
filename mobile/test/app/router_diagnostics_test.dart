import 'dart:io';

import 'package:ai_stock_studio/app/router.dart';
import 'package:ai_stock_studio/features/auth/presentation/auth_controller.dart';
import 'package:ai_stock_studio/features/settings/data/network_diagnostics.dart';
import 'package:ai_stock_studio/features/settings/presentation/diagnostics_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

/// `/diagnostics` must be reachable in BOTH auth states: pre-login (a
/// failed sign-in is exactly when it is needed) and post-login.
void main() {
  NetworkDiagnostics fakeService() => NetworkDiagnostics(
        relayPort: 42142,
        systemLookup: (String h) async =>
            <InternetAddress>[InternetAddress('104.21.73.125')],
        dohFetch: (Uri url, Map<String, String> h) async => '{"Status":0}',
        udpQuery: (String s, List<int> p, Duration t) async =>
            throw const SocketException('blocked'),
        transport: (String url, {String? proxy}) async => 'HTTP 200 in 1 ms',
        tcpConnect: (InternetAddress a, int p, Duration t) async {},
      );

  Future<void> pumpAt(
    WidgetTester tester,
    AuthStatus status,
    String location,
  ) async {
    final ValueNotifier<AuthStatus> listenable =
        ValueNotifier<AuthStatus>(status);
    final GoRouter router = createRouter(
      currentStatus: () => listenable.value,
      refreshListenable: listenable,
      initialLocation: location,
    );
    addTearDown(router.dispose);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [diagnosticsProvider.overrideWithValue(fakeService())],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('unauthenticated can open /diagnostics (pre-login triage)',
      (tester) async {
    await pumpAt(tester, AuthStatus.unauthenticated, '/diagnostics');
    expect(find.byType(DiagnosticsScreen), findsOneWidget);
  });

  testWidgets('authenticated can open /diagnostics too', (tester) async {
    await pumpAt(tester, AuthStatus.authenticated, '/diagnostics');
    expect(find.byType(DiagnosticsScreen), findsOneWidget);
  });
}
