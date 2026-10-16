import 'dart:io';

import 'package:ai_stock_studio/features/settings/data/network_diagnostics.dart';
import 'package:ai_stock_studio/features/settings/presentation/diagnostics_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

/// The screen renders every layer with full, selectable detail and can be
/// re-run — the surface the user screenshots when a phone can't connect.
void main() {
  NetworkDiagnostics fakeService() => NetworkDiagnostics(
        relayPort: 42142,
        systemLookup: (String h) async =>
            <InternetAddress>[InternetAddress('104.21.73.125')],
        dohFetch: (Uri url, Map<String, String> h) async =>
            '{"Status":0,"Answer":[{"type":1,"TTL":300,'
            '"data":"172.67.190.8"}]}',
        udpQuery: (String s, List<int> p, Duration t) async =>
            throw const SocketException('UDP blocked'),
        transport: (String url, {String? proxy}) async =>
            'HTTP 200 in 12 ms',
        tcpConnect: (InternetAddress a, int p, Duration t) async {},
      );

  Future<void> pumpScreen(WidgetTester tester) async {
    // Tall phone viewport — ListView materializes children lazily even
    // with an explicit children list, so all 9 rows must fit on screen.
    tester.view.physicalSize = const Size(1080, 3000);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [diagnosticsProvider.overrideWithValue(fakeService())],
        child: const MaterialApp(home: DiagnosticsScreen()),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('auto-runs on open and lists every layer', (tester) async {
    await pumpScreen(tester);
    expect(find.text('SYSTEM RESOLVER'), findsOneWidget);
    expect(find.text('DOH 1.1.1.1 (IPV4)'), findsOneWidget);
    expect(find.text('RELAY (CONNECT PROXY)'), findsOneWidget);
    expect(find.text('TUNNEL /HEALTH — APP PATH'), findsOneWidget);
    expect(find.text('HTTP 200 in 12 ms'), findsWidgets);
    expect(find.textContaining('104.21.73.125'), findsWidgets);
    expect(find.byType(CircularProgressIndicator), findsNothing);
  });

  testWidgets('Run again re-executes the checks', (tester) async {
    await pumpScreen(tester);
    await tester.tap(find.text('Run again'));
    await tester.pumpAndSettle();
    expect(find.text('SYSTEM RESOLVER'), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsNothing);
  });
}
