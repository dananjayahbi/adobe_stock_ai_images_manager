import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';

import 'package:ai_stock_studio/app/theme/theme.dart';
import 'package:ai_stock_studio/core/utils/app_exception.dart';
import 'package:ai_stock_studio/core/utils/ui_message.dart';
import 'package:ai_stock_studio/features/auth/data/auth_repository_impl.dart';
import 'package:ai_stock_studio/features/auth/domain/auth_repository.dart';
import 'package:ai_stock_studio/features/auth/presentation/login_form.dart';
import 'package:ai_stock_studio/features/auth/presentation/login_screen.dart';
import 'package:ai_stock_studio/features/settings/data/profile_store.dart';
import 'package:shared_preferences/shared_preferences.dart';

class FakeAuthRepository implements AuthRepository {
  FakeAuthRepository({this.onLogin});

  Future<void> Function(String username, String password)? onLogin;
  int loginCalls = 0;

  @override
  Future<void> login(String username, String password) {
    loginCalls += 1;
    return onLogin?.call(username, password) ?? Future<void>.value();
  }

  @override
  Future<bool> sessionAlive() async => false;

  @override
  Future<void> logout() async {}
}

void main() {
  setUpAll(() {
    // Never hit fonts.google.com from tests (03 §5).
    GoogleFonts.config.allowRuntimeFetching = false;
  });

  // LoginScreen renders the pre-auth connection row, which reads the
  // profile store from SharedPreferences.
  late SharedPreferences prefs;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    prefs = await SharedPreferences.getInstance();
  });

  Widget host({required Widget child, required AuthRepository repo}) {
    return ProviderScope(
      overrides: [
        authRepositoryProvider.overrideWithValue(repo),
        sharedPreferencesProvider.overrideWithValue(prefs),
      ],
      child: MaterialApp(
        theme: buildAppTheme(),
        // LoginForm is pumped bare in most cases — give it the Material
        // ancestor that TextField requires.
        home: Scaffold(body: child),
      ),
    );
  }

  Future<void> fillCredentials(WidgetTester tester) async {
    await tester.enterText(find.byType(TextFormField).at(0), 'admin');
    await tester.enterText(find.byType(TextFormField).at(1), 'wrong');
  }

  testWidgets('initial state renders wordmark and visible field labels', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      host(child: const LoginScreen(), repo: FakeAuthRepository()),
    );
    await tester.pump(const Duration(milliseconds: 400));

    expect(find.text('AI STOCK STUDIO'), findsOneWidget);
    expect(find.text('Username'), findsOneWidget);
    expect(find.text('Password'), findsOneWidget);
    expect(find.text('Sign in'), findsOneWidget);
  });

  testWidgets('AuthException shows inline error under the form', (
    WidgetTester tester,
  ) async {
    final FakeAuthRepository repo = FakeAuthRepository(
      onLogin: (String _, String _) {
        throw const AuthException(message: 'Invalid credentials');
      },
    );
    await tester.pumpWidget(
      host(child: const LoginForm(), repo: repo),
    );
    await tester.pump();

    await fillCredentials(tester);
    await tester.tap(find.text('Sign in'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(repo.loginCalls, 1);
    expect(find.text("Those keys didn't fit."), findsOneWidget);
    expect(
      find.text(uiMessageFor(const AuthException(message: 'Invalid credentials'))),
      findsOneWidget,
    );
  });

  testWidgets('submitting shows progress and disables re-entry', (
    WidgetTester tester,
  ) async {
    final Completer<void> gate = Completer<void>();
    final FakeAuthRepository repo = FakeAuthRepository(
      onLogin: (String _, String _) => gate.future,
    );
    await tester.pumpWidget(
      host(child: const LoginForm(), repo: repo),
    );
    await tester.pump();

    await fillCredentials(tester);
    await tester.tap(find.text('Sign in'));
    await tester.pump();

    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    // Double-tap while in flight: still exactly one login call.
    await tester.tap(find.text('Sign in'), warnIfMissed: false);
    await tester.pump();
    expect(repo.loginCalls, 1);

    // Leave `gate` incomplete on purpose — no navigation fires without a
    // router, and a never-completing future is not a pending timer.
  });

  testWidgets('success fires the onLogin navigation callback', (
    WidgetTester tester,
  ) async {
    bool navigated = false;
    final FakeAuthRepository repo = FakeAuthRepository();
    await tester.pumpWidget(
      host(
        child: LoginForm(onAuthenticated: () => navigated = true),
        repo: repo,
      ),
    );
    await tester.pump();

    await fillCredentials(tester);
    await tester.tap(find.text('Sign in'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(repo.loginCalls, 1);
    expect(navigated, isTrue);
  });
}
