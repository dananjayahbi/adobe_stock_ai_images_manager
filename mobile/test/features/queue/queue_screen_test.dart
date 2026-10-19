import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:ai_stock_studio/app/theme/theme.dart';
import 'package:ai_stock_studio/features/queue/data/queue_repository.dart';
import 'package:ai_stock_studio/features/queue/domain/queue_item.dart';
import 'package:ai_stock_studio/features/queue/presentation/queue_controller.dart';
import 'package:ai_stock_studio/features/queue/presentation/queue_indicator_bar.dart';
import 'package:ai_stock_studio/features/queue/presentation/queue_screen.dart';
import 'package:ai_stock_studio/features/settings/data/profile_store.dart';

/// In-flight promote stand-in (see queue_controller_test).
class _FakeQueueRepository implements QueueRepository {
  final List<String> order = <String>[];
  final Map<String, Completer<void>> pending = <String, Completer<void>>{};

  @override
  Future<void> promoteOne(String recordId) {
    order.add(recordId);
    final Completer<void> completer = Completer<void>();
    pending[recordId] = completer;
    return completer.future;
  }

  void succeed(String recordId) => pending.remove(recordId)!.complete();

  void fail(String recordId, Object error) =>
      pending.remove(recordId)!.completeError(error);
}

void main() {
  setUpAll(() {
    GoogleFonts.config.allowRuntimeFetching = false;
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  late _FakeQueueRepository fake;

  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    fake = _FakeQueueRepository();
  });

  Future<Widget> harness(Widget child) async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    return ProviderScope(
      overrides: [
        queueRepositoryProvider.overrideWithValue(fake),
        sharedPreferencesProvider.overrideWithValue(prefs),
      ],
      child: MaterialApp(theme: buildAppTheme(), home: child),
    );
  }

  Future<void> pumpScreen(WidgetTester tester) async {
    await tester.pumpWidget(await harness(const QueueScreen()));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
  }

  /// Drain runner microtasks — widget tests run on the fake clock, so
  /// `pumpEventQueue` (a zero timer) would deadlock; a pump is enough
  /// because every loop step is driven by Completer microtasks.
  Future<void> flush(WidgetTester tester) async {
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 1));
  }

  testWidgets('empty queue shows the empty state, idle banner and Start', (
    WidgetTester tester,
  ) async {
    await pumpScreen(tester);

    expect(find.text('Nothing queued'), findsOneWidget);
    expect(
      find.text('Idle — press Start to begin.'),
      findsOneWidget,
    );
    expect(find.text('Start'), findsOneWidget);
    expect(find.text('Pause'), findsNothing);
  });

  testWidgets('Start runs items sequentially with a running banner and '
      'Pause control', (WidgetTester tester) async {
    await pumpScreen(tester);

    final ProviderContainer scope = ProviderScope.containerOf(
      tester.element(find.byType(QueueScreen)),
    );
    await scope.read(queueProvider.notifier).enqueue('a', filename: 'a.jpg');
    await scope.read(queueProvider.notifier).enqueue('b', filename: 'b.jpg');
    await tester.pump();
    expect(find.text('a.jpg'), findsOneWidget);
    expect(find.text('b.jpg'), findsOneWidget);
    expect(find.text('Waiting'), findsNWidgets(2));

    await tester.tap(find.text('Start'));
    await tester.pump();
    await flush(tester);

    expect(
      find.text('Running — promoting one image at a time.'),
      findsOneWidget,
    );
    expect(find.text('Pause'), findsOneWidget);
    expect(find.text('Start'), findsNothing);
    expect(find.text('Running'), findsOneWidget); // a is in flight
    expect(scope.read(queueProvider).currentId, 'a');

    // Pause: banner flips immediately; the current item still finishes.
    await tester.tap(find.text('Pause'));
    await tester.pump();
    await flush(tester);
    expect(find.text('Paused · 1 waiting. Press Start to resume.'), findsOneWidget);
    expect(find.text('Start'), findsOneWidget);

    fake.succeed('a');
    await flush(tester);
    await tester.pump();
    expect(
      scope.read(queueProvider).byId('a')!.status,
      QueueItemStatus.done,
    );
    expect(find.text('Done'), findsOneWidget);
    expect(
      scope.read(queueProvider).byId('b')!.status,
      QueueItemStatus.waiting,
    );

    // Resume → b starts.
    await tester.tap(find.text('Start'));
    await tester.pump();
    await flush(tester);
    expect(scope.read(queueProvider).currentId, 'b');
    fake.succeed('b');
    await flush(tester);
    await tester.pump();
    expect(
      find.text('Waiting for next image — new approvals join the queue.'),
      findsOneWidget,
    );
  });

  testWidgets('failed item shows its reason with Retry and Remove; Retry '
      're-queues it', (WidgetTester tester) async {
    await pumpScreen(tester);
    final ProviderContainer scope = ProviderScope.containerOf(
      tester.element(find.byType(QueueScreen)),
    );
    await scope.read(queueProvider.notifier).enqueue('a', filename: 'a.jpg');
    await tester.pump();

    await tester.tap(find.text('Start'));
    await tester.pump();
    await flush(tester);

    fake.fail('a', NetworkishFailure());
    await flush(tester);
    await tester.pump();

    expect(find.text('Failed'), findsOneWidget);
    expect(find.text('promote refused'), findsOneWidget);
    expect(find.byTooltip('Retry'), findsOneWidget);
    expect(find.byTooltip('Remove from queue'), findsOneWidget);

    await tester.tap(find.byTooltip('Retry'));
    await tester.pump();
    await flush(tester);

    // Runner stayed alive (waiting) → retry auto-picked the item up.
    expect(find.text('Running'), findsOneWidget);
    expect(find.text('promote refused'), findsNothing);

    fake.succeed('a');
    await flush(tester);
    await tester.pump();
    expect(find.text('Done'), findsOneWidget);

    // Remove takes it out of the deque entirely.
    await tester.tap(find.byTooltip('Remove from queue'));
    await tester.pump();
    await flush(tester);
    expect(find.text('Nothing queued'), findsOneWidget);
  });

  testWidgets('Clear action hides while nothing is processed, clears '
      'done/failed rows on tap, and leaves waiting/running alone', (
    WidgetTester tester,
  ) async {
    await pumpScreen(tester);
    final ProviderContainer scope = ProviderScope.containerOf(
      tester.element(find.byType(QueueScreen)),
    );
    final QueueController controller = scope.read(queueProvider.notifier);

    // Waiting-only queue: no dead Clear button in the AppBar.
    expect(find.byTooltip('Clear processed items'), findsNothing);

    await controller.enqueue('a', filename: 'a.jpg');
    await controller.enqueue('b', filename: 'b.jpg');
    await tester.pump();
    expect(find.byTooltip('Clear processed items'), findsNothing);

    await tester.tap(find.text('Start'));
    await tester.pump();
    await flush(tester);

    // a succeeds (done), b is now running; d-style waiting stays via a
    // third item enqueued pre-start would be picked up — enqueue after
    // start with the runner alive also auto-picks up, so instead pause
    // is not needed: we only need one waiting survivor. Enqueue c now
    // while b is in flight: it waits.
    await controller.enqueue('c', filename: 'c.jpg');
    await tester.pump();

    fake.succeed('a');
    await flush(tester);
    await tester.pump();
    expect(scope.read(queueProvider).byId('a')!.status, QueueItemStatus.done);
    // One done row → the Clear action exists.
    expect(find.byTooltip('Clear processed items'), findsOneWidget);

    await tester.tap(find.byTooltip('Clear processed items'));
    await tester.pump();
    await flush(tester);

    // done row gone; running (b) and waiting (c) untouched.
    expect(scope.read(queueProvider).byId('a'), isNull);
    expect(scope.read(queueProvider).byId('b')!.status, QueueItemStatus.running);
    expect(scope.read(queueProvider).byId('c')!.status, QueueItemStatus.waiting);
    expect(find.text('a.jpg'), findsNothing);
    expect(find.text('b.jpg'), findsOneWidget);
    expect(find.text('c.jpg'), findsOneWidget);
    // Nothing terminal left → button hidden again (no dead button).
    expect(find.byTooltip('Clear processed items'), findsNothing);

    // Fail b → failed row re-enables Clear; c picked up as running.
    fake.fail('b', NetworkishFailure());
    await flush(tester);
    await tester.pump();
    expect(
      scope.read(queueProvider).byId('b')!.status,
      QueueItemStatus.failed,
    );
    expect(find.byTooltip('Clear processed items'), findsOneWidget);

    await tester.tap(find.byTooltip('Clear processed items'));
    await tester.pump();
    await flush(tester);
    expect(scope.read(queueProvider).byId('b'), isNull);
    // The running/waiting c line survives a second clear.
    expect(
      scope.read(queueProvider).byId('c')!.status,
      QueueItemStatus.running,
    );
    expect(find.byTooltip('Clear processed items'), findsNothing);
  });

  group('QueueIndicatorBar (R3)', () {
    Future<void> pumpIndicator(
      WidgetTester tester,
      List<String> taps,
    ) async {
      await tester.pumpWidget(
        await harness(
          Scaffold(
            bottomNavigationBar: QueueIndicatorBar(
              onOpenQueue: () => taps.add('open'),
            ),
          ),
        ),
      );
      await tester.pump();
    }

    testWidgets('hidden while the queue is idle and empty; shows after an '
        'enqueue; hides again when drained and cleared', (
      WidgetTester tester,
    ) async {
      final List<String> taps = <String>[];
      await pumpIndicator(tester, taps);

      // Idle + empty → no bar at all (documented visibility contract).
      expect(find.byTooltip('Start queue'), findsNothing);
      expect(find.textContaining('Queue · '), findsNothing);

      final ProviderContainer scope = ProviderScope.containerOf(
        tester.element(find.byType(QueueIndicatorBar)),
      );
      await scope.read(queueProvider.notifier).enqueue(
            'a',
            filename: 'wire_loop.jpg',
          );
      await tester.pump();

      expect(find.text('Queue · 1 waiting'), findsOneWidget);
      expect(find.byTooltip('Start queue'), findsOneWidget);

      // Play starts the runner; the status tracks the running item.
      await tester.tap(find.byTooltip('Start queue'));
      await tester.pump();
      await flush(tester);
      expect(
        find.text('Queue · 0 waiting — running wire_loop.jpg'),
        findsOneWidget,
      );
      expect(find.byTooltip('Pause queue'), findsOneWidget);

      // Drained → the started runner keeps the bar up: "waiting for next
      // image" (the next approval auto-picks up).
      fake.succeed('a');
      await flush(tester);
      expect(find.text('Queue · waiting for next image'), findsOneWidget);

      // Pause stops the (empty) runner → paused copy, bar still up because
      // the deque still holds the finished item.
      await tester.tap(find.byTooltip('Pause queue'));
      await tester.pump();
      await flush(tester);
      expect(find.textContaining('paused'), findsOneWidget);

      // Clearing the deque while nothing runs hides the bar again.
      await scope.read(queueProvider.notifier).remove('a');
      await tester.pump();
      expect(find.textContaining('Queue · '), findsNothing);
      expect(find.byTooltip('Start queue'), findsNothing);
    });

    testWidgets('tapping the bar opens the Queue tab (except the '
        'play/pause button, which toggles instead)', (WidgetTester tester) async {
      final List<String> taps = <String>[];
      await pumpIndicator(tester, taps);

      final ProviderContainer scope = ProviderScope.containerOf(
        tester.element(find.byType(QueueIndicatorBar)),
      );
      await scope.read(queueProvider.notifier).enqueue(
            'a',
            filename: 'a.jpg',
          );
      await tester.pump();

      await tester.tap(find.text('Queue · 1 waiting'));
      await tester.pump();
      expect(taps, <String>['open']);

      // The icon button stops propagation: toggles, does not navigate.
      await tester.tap(find.byTooltip('Start queue'));
      await tester.pump();
      await flush(tester);
      expect(taps, <String>['open']); // unchanged
      expect(scope.read(queueProvider).runner, isNot(QueueRunnerStatus.idle));
    });
  });
}

/// Failure type with a message the queue should surface verbatim.
class NetworkishFailure implements Exception {
  @override
  String toString() => 'promote refused';
}

