import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ai_stock_studio/app/lifecycle_observer.dart';

void main() {
  setUp(AppLifecycleHooks.reset);
  tearDown(AppLifecycleHooks.reset);

  test('resumed runs the session callback then every feature invalidator, '
      'once each', () async {
    final List<String> calls = <String>[];
    AppLifecycleHooks.onResume = () async {
      calls.add('session');
    };
    AppLifecycleHooks.registerFeatureInvalidator(
      'dashboard',
      () => calls.add('dashboard'),
    );
    AppLifecycleHooks.registerFeatureInvalidator(
      'gallery',
      () => calls.add('gallery'),
    );
    final AppLifecycleObserver observer = AppLifecycleObserver();

    observer.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await pumpEventQueue();

    // Session revalidation first, then provider invalidation (03 §4).
    expect(calls, <String>['session', 'dashboard', 'gallery']);
    expect(observer.lastState, AppLifecycleState.resumed);
    expect(observer.isInactive, isFalse);
  });

  test('feature invalidation still runs when no session hook is registered',
      () async {
    int invalidated = 0;
    AppLifecycleHooks.registerFeatureInvalidator(
      'process',
      () => invalidated++,
    );
    final AppLifecycleObserver observer = AppLifecycleObserver();

    observer.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await pumpEventQueue();

    expect(invalidated, 1);
    expect(observer.isInactive, isFalse);
  });

  test('paused marks inactive without firing hooks; resumed clears it',
      () async {
    int resumed = 0;
    int invalidated = 0;
    AppLifecycleHooks.onResume = () async {
      resumed++;
    };
    AppLifecycleHooks.registerFeatureInvalidator(
      'delivery',
      () => invalidated++,
    );
    final AppLifecycleObserver observer = AppLifecycleObserver();

    observer.didChangeAppLifecycleState(AppLifecycleState.paused);
    await pumpEventQueue();

    expect(observer.lastState, AppLifecycleState.paused);
    expect(observer.isInactive, isTrue);
    expect(resumed, 0);
    expect(invalidated, 0);

    observer.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await pumpEventQueue();

    expect(observer.isInactive, isFalse);
    expect(resumed, 1);
    expect(invalidated, 1);
  });

  test('a throwing session hook cannot skip feature invalidation', () async {
    AppLifecycleHooks.onResume = () async => throw StateError('boom');
    int invalidated = 0;
    AppLifecycleHooks.registerFeatureInvalidator(
      'gallery',
      () => invalidated++,
    );
    final AppLifecycleObserver observer = AppLifecycleObserver();

    observer.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await pumpEventQueue();

    expect(invalidated, 1);
    expect(observer.isInactive, isFalse);
  });

  test('each resume invalidates again; re-registering a key replaces it',
      () async {
    int first = 0;
    int second = 0;
    AppLifecycleHooks.registerFeatureInvalidator('key', () => first++);
    AppLifecycleHooks.registerFeatureInvalidator('key', () => second++);
    final AppLifecycleObserver observer = AppLifecycleObserver();

    observer.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await pumpEventQueue();
    expect(first, 0);
    expect(second, 1);

    observer.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await pumpEventQueue();
    expect(second, 2);
  });

  test('resume with nothing registered is a no-op', () async {
    final AppLifecycleObserver observer = AppLifecycleObserver();

    observer.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await pumpEventQueue();

    expect(observer.lastState, AppLifecycleState.resumed);
    expect(observer.isInactive, isFalse);
  });
}
