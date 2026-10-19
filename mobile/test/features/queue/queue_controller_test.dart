import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:ai_stock_studio/core/utils/app_exception.dart';
import 'package:ai_stock_studio/features/queue/data/queue_repository.dart';
import 'package:ai_stock_studio/features/queue/domain/queue_item.dart';
import 'package:ai_stock_studio/features/queue/domain/queue_state.dart';
import 'package:ai_stock_studio/features/queue/presentation/queue_controller.dart';
import 'package:ai_stock_studio/features/settings/data/profile_store.dart';

/// Scriptable promote stand-in: each `promoteOne` call parks on a completer
/// the test finishes by hand (sequential + pause-after-current semantics
/// need deterministic in-flight moments).
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

/// Flushes microtasks + zero-timers between runner steps.
Future<void> flush() => pumpEventQueue();

void main() {
  setUpAll(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  late _FakeQueueRepository fake;
  late SharedPreferences prefs;

  Future<ProviderContainer> makeContainer() async {
    prefs = await SharedPreferences.getInstance();
    final ProviderContainer container = ProviderContainer(
      overrides: [
        queueRepositoryProvider.overrideWithValue(fake),
        sharedPreferencesProvider.overrideWithValue(prefs),
      ],
    );
    container.read(queueProvider); // Force the (restoring) build.
    await flush();
    return container;
  }

  setUp(() async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    fake = _FakeQueueRepository();
  });

  test('start drains sequentially — one in-flight item at a time', () async {
    final ProviderContainer container = await makeContainer();
    addTearDown(container.dispose);
    final QueueController controller = container.read(queueProvider.notifier);

    await controller.enqueue('a', filename: 'a.jpg');
    await controller.enqueue('b', filename: 'b.jpg');

    // Never started → items wait; the runner does not auto-start (Start is
    // the explicit gate, documented in queue_controller.dart).
    expect(container.read(queueProvider).runner, QueueRunnerStatus.idle);
    expect(fake.order, isEmpty);

    await controller.start();
    await flush();
    QueueState state = container.read(queueProvider);
    expect(state.runner, QueueRunnerStatus.running);
    expect(state.currentId, 'a');
    expect(state.byId('a')!.status, QueueItemStatus.running);
    expect(state.byId('b')!.status, QueueItemStatus.waiting);
    expect(fake.order, <String>['a']); // strictly sequential

    fake.succeed('a');
    await flush();
    state = container.read(queueProvider);
    expect(state.currentId, 'b');
    expect(state.byId('a')!.status, QueueItemStatus.done);
    expect(fake.order, <String>['a', 'b']);

    fake.succeed('b');
    await flush();
    state = container.read(queueProvider);
    expect(state.byId('b')!.status, QueueItemStatus.done);
    expect(state.currentId, isNull);
    // Empty while started → "waiting for next image" (runner stays alive).
    expect(state.runner, QueueRunnerStatus.waiting);
  });

  test('pause lets the CURRENT item finish, then stops (Start resumes)',
      () async {
    final ProviderContainer container = await makeContainer();
    addTearDown(container.dispose);
    final QueueController controller = container.read(queueProvider.notifier);

    await controller.enqueue('a', filename: 'a.jpg');
    await controller.enqueue('b', filename: 'b.jpg');
    await controller.start();
    await flush();

    await controller.pause();
    // Intent is immediate: `paused` while 'a' is still in flight…
    expect(container.read(queueProvider).runner, QueueRunnerStatus.paused);

    // …but the current item still completes, and b never starts.
    fake.succeed('a');
    await flush();
    QueueState state = container.read(queueProvider);
    expect(state.byId('a')!.status, QueueItemStatus.done);
    expect(state.byId('b')!.status, QueueItemStatus.waiting);
    expect(state.runner, QueueRunnerStatus.paused);
    expect(state.currentId, isNull);
    expect(fake.order, <String>['a']);

    // Start resumes instantly with the next waiting item.
    await controller.start();
    await flush();
    state = container.read(queueProvider);
    expect(state.runner, QueueRunnerStatus.running);
    expect(state.currentId, 'b');
    expect(fake.order, <String>['a', 'b']);

    fake.succeed('b');
    await flush();
    expect(container.read(queueProvider).runner, QueueRunnerStatus.waiting);
  });

  test('empty started queue waits; an enqueue auto-picks up without Start',
      () async {
    final ProviderContainer container = await makeContainer();
    addTearDown(container.dispose);
    final QueueController controller = container.read(queueProvider.notifier);

    await controller.start();
    await flush();
    expect(
      container.read(queueProvider).runner,
      QueueRunnerStatus.waiting, // "waiting for next image"
    );
    expect(fake.order, isEmpty);

    // Runner is logically alive → approval's enqueue is picked up at once.
    await controller.enqueue('c', filename: 'wire_loop.jpg');
    await flush();
    final QueueState state = container.read(queueProvider);
    expect(state.runner, QueueRunnerStatus.running);
    expect(state.currentId, 'c');
    expect(state.byId('c')!.status, QueueItemStatus.running);
    expect(fake.order, <String>['c']);

    fake.succeed('c');
    await flush();
    expect(container.read(queueProvider).runner, QueueRunnerStatus.waiting);
  });

  test('a failed item records its reason and the runner continues', () async {
    final ProviderContainer container = await makeContainer();
    addTearDown(container.dispose);
    final QueueController controller = container.read(queueProvider.notifier);

    await controller.enqueue('a', filename: 'a.jpg');
    await controller.enqueue('b', filename: 'b.jpg');
    await controller.start();
    await flush();

    fake.fail('a', const ValidationException(message: 'OCR blocks promote.'));
    await flush();
    QueueState state = container.read(queueProvider);
    expect(state.byId('a')!.status, QueueItemStatus.failed);
    expect(state.byId('a')!.error, 'OCR blocks promote.');
    // Failure never wedges the drain — next item is already running.
    expect(state.currentId, 'b');
    expect(fake.order, <String>['a', 'b']);

    fake.succeed('b');
    await flush();
    state = container.read(queueProvider);
    expect(state.byId('b')!.status, QueueItemStatus.done);
    expect(state.runner, QueueRunnerStatus.waiting);

    // Retry re-queues the failed line and — runner alive — picks it up.
    await controller.retry('a');
    await flush();
    state = container.read(queueProvider);
    expect(state.byId('a')!.status, QueueItemStatus.running);
    expect(state.byId('a')!.error, isNull);
    expect(fake.order, <String>['a', 'b', 'a']);

    fake.succeed('a');
    await flush();
    expect(container.read(queueProvider).byId('a')!.status, QueueItemStatus.done);

    // Remove drops a finished item from the list.
    await controller.remove('b');
    await flush();
    expect(container.read(queueProvider).byId('b'), isNull);
  });

  test('clearProcessed drops done/failed only and persists the pruned '
      'deque (waiting/running survive)', () async {
    final ProviderContainer container = await makeContainer();
    addTearDown(container.dispose);
    final QueueController controller = container.read(queueProvider.notifier);

    // a done, b failed, c running (in flight), d waiting — all four
    // statuses live at once so the filter is unambiguous.
    await controller.enqueue('a', filename: 'a.jpg');
    await controller.enqueue('b', filename: 'b.jpg');
    await controller.enqueue('c', filename: 'c.jpg');
    await controller.enqueue('d', filename: 'd.jpg');
    await controller.start();
    await flush();
    fake.succeed('a');
    await flush();
    fake.fail('b', const ValidationException(message: 'OCR blocks promote.'));
    await flush();

    QueueState state = container.read(queueProvider);
    expect(state.byId('a')!.status, QueueItemStatus.done);
    expect(state.byId('b')!.status, QueueItemStatus.failed);
    expect(state.byId('c')!.status, QueueItemStatus.running);
    expect(state.byId('d')!.status, QueueItemStatus.waiting);
    expect(state.currentId, 'c');

    await controller.clearProcessed();
    await flush();

    state = container.read(queueProvider);
    expect(state.byId('a'), isNull); // done → cleared
    expect(state.byId('b'), isNull); // failed → cleared
    expect(state.byId('c')!.status, QueueItemStatus.running); // never touched
    expect(state.byId('d')!.status, QueueItemStatus.waiting); // never touched
    expect(state.currentId, 'c'); // in-flight id preserved
    expect(state.runner, QueueRunnerStatus.running);

    // Persistence called: the stored snapshot is already the pruned one,
    // so a restart cannot resurrect the cleared rows.
    final String? raw = prefs.getString(QueueStorage.kQueueStorageKey);
    expect(raw, isNotNull);
    final QueueState persisted = decodeQueueSnapshot(raw!);
    expect(
      persisted.items.map((QueueItem item) => item.recordId).toList(),
      <String>['c', 'd'],
    );

    // The in-flight promote continues uninterrupted after the clear.
    fake.succeed('c');
    await flush();
    state = container.read(queueProvider);
    expect(state.byId('c')!.status, QueueItemStatus.done);
    expect(state.currentId, 'd');
  });

  test('clearProcessed on a queue without processed items is a no-op', () async {
    final ProviderContainer container = await makeContainer();
    addTearDown(container.dispose);
    final QueueController controller = container.read(queueProvider.notifier);

    await controller.enqueue('w', filename: 'w.jpg');
    final QueueState before = container.read(queueProvider);

    await controller.clearProcessed();
    await flush();

    final QueueState after = container.read(queueProvider);
    expect(identical(before, after), isTrue); // no commit happened
    expect(after.items, hasLength(1));
    expect(after.byId('w')!.status, QueueItemStatus.waiting);
  });

  test('persistence round-trip: waiting items survive, restart maps '
      'running → paused (documented policy)', () async {
    // Phase 1 — a live container writes its deque to SharedPreferences.
    final ProviderContainer first = await makeContainer();
    final QueueController controller = first.read(queueProvider.notifier);
    await controller.enqueue('a', filename: 'a.jpg');
    await controller.enqueue('b', filename: 'b.jpg');
    first.dispose();

    // A fresh container (same store) restores the same deque.
    final ProviderContainer second = await makeContainer();
    addTearDown(second.dispose);
    QueueState restored = second.read(queueProvider);
    expect(
      restored.items.map((QueueItem item) => item.recordId).toList(),
      <String>['a', 'b'],
    );
    expect(restored.items.every((QueueItem i) => i.status == QueueItemStatus.waiting), isTrue);
    expect(restored.runner, QueueRunnerStatus.idle);

    // Phase 2 — a snapshot written mid-run (restart while promoting):
    // the in-flight item falls back to waiting, the runner becomes paused,
    // and nothing resumes until Start.
    await prefs.setString(
      QueueStorage.kQueueStorageKey,
      encodeQueueSnapshot(
        QueueState(
          items: const <QueueItem>[
            QueueItem(
              recordId: 'x',
              filename: 'x.jpg',
              status: QueueItemStatus.running,
            ),
            QueueItem(recordId: 'w', filename: 'w.jpg'),
          ],
          runner: QueueRunnerStatus.running,
          currentId: 'x',
        ),
      ),
    );
    final ProviderContainer third = await makeContainer();
    addTearDown(third.dispose);
    restored = third.read(queueProvider);
    expect(
      restored.items.map((QueueItem item) => item.recordId).toList(),
      <String>['x', 'w'],
    );
    expect(restored.byId('x')!.status, QueueItemStatus.waiting);
    expect(restored.runner, QueueRunnerStatus.paused);
    expect(restored.currentId, isNull);
    // No auto-resume after a restart: the fake never got called.
    expect(fake.order, isEmpty);
  });

  test('paused runner does not auto-start on enqueue; Start picks up both',
      () async {
    final ProviderContainer container = await makeContainer();
    addTearDown(container.dispose);
    final QueueController controller = container.read(queueProvider.notifier);

    await controller.start(); // empty → waiting (alive)
    await flush();
    await controller.pause();
    await flush();
    expect(container.read(queueProvider).runner, QueueRunnerStatus.paused);

    await controller.enqueue('p', filename: 'p.jpg');
    await flush();
    // Pause was an explicit stop — the item waits for Start.
    expect(container.read(queueProvider).runner, QueueRunnerStatus.paused);
    expect(container.read(queueProvider).currentId, isNull);
    expect(fake.order, isEmpty);

    await controller.start();
    await flush();
    expect(container.read(queueProvider).currentId, 'p');
    expect(fake.order, <String>['p']);
  });
}
