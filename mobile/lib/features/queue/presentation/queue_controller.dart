import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../settings/data/profile_store.dart';
import '../data/queue_repository.dart';
import '../domain/queue_item.dart';
import '../domain/queue_state.dart';

/// App-level readiness queue (R3): one deque of records waiting for the
/// promote check/run pass, one sequential runner, persisted to
/// SharedPreferences so a restart restores waiting items.
final queueProvider = NotifierProvider<QueueController, QueueState>(
  QueueController.new,
);

/// Sequential promote runner.
///
/// Semantics (user contract, R3):
/// * **Start** drains the deque one record at a time; Start after
///   idle/paused (or while [QueueRunnerStatus.waiting]) resumes instantly.
/// * **Pause** lets the CURRENT item finish, then stops (runner →
///   `paused`).
/// * Empty queue while started → `waiting` ("waiting for next image"):
///   the runner stays logically alive, so the next enqueue is auto-picked
///   up without pressing Start again. A never-started (`idle`) runner only
///   accumulates — Start (or a live runner's pickup) begins the work.
/// * A failed item is marked `failed` with its reason and the runner
///   moves straight on to the next one.
///
/// Enqueue/retry from `idle`/`paused` does NOT auto-start (Start is the
/// explicit gate); from `running`/`waiting` it is picked up immediately.
class QueueController extends Notifier<QueueState> {
  /// True while the async drain loop below is between its top and exit.
  bool _loopActive = false;

  /// Set by [pause]; checked at the top of every loop iteration so the
  /// in-flight item always finishes first.
  bool _pauseRequested = false;

  bool _disposed = false;

  /// Completed by [start]/[enqueue] to wake a loop sleeping on an empty
  /// queue; re-created by [_sleep] once consumed.
  Completer<void> _wakeup = Completer<void>();

  late QueueStorage _storage;

  @override
  QueueState build() {
    _storage = QueueStorage(ref.watch(sharedPreferencesProvider));
    ref.onDispose(() => _disposed = true);
    // Synchronous restore: SharedPreferences' in-memory cache is ready the
    // moment the instance exists (main awaits it before runApp), so a
    // cold start paints the waiting items with no loading flash.
    return _storage.load();
  }

  /// Queue [recordId] for promote (Approve / change-state → READY).
  /// Duplicate waiting/running ids are ignored; a done/failed item is
  /// re-queued fresh.
  Future<void> enqueue(String recordId, {String filename = ''}) async {
    if (recordId.isEmpty || _disposed) {
      return;
    }
    final List<QueueItem> items = List<QueueItem>.of(state.items);
    final int at = items.indexWhere(
      (QueueItem item) => item.recordId == recordId,
    );
    if (at >= 0) {
      final QueueItem existing = items[at];
      if (existing.status == QueueItemStatus.waiting ||
          existing.status == QueueItemStatus.running) {
        return;
      }
      items[at] = QueueItem(
        recordId: recordId,
        filename: filename.isEmpty ? existing.filename : filename,
      );
    } else {
      items.add(QueueItem(recordId: recordId, filename: filename));
    }
    _commit(
      QueueState(
        items: items,
        runner: state.runner,
        currentId: state.currentId,
      ),
    );
    await _persist();
    _kickIfLive();
  }

  /// Re-queue a failed item (clears its error) under the same pickup
  /// rules as [enqueue].
  Future<void> retry(String recordId) async {
    final QueueItem? item = state.byId(recordId);
    if (item == null || item.status != QueueItemStatus.failed || _disposed) {
      return;
    }
    final List<QueueItem> items = List<QueueItem>.of(state.items);
    final int at = items.indexWhere(
      (QueueItem queueItem) => queueItem.recordId == recordId,
    );
    items[at] = item.copyWith(
      status: QueueItemStatus.waiting,
      clearError: true,
    );
    _commit(
      QueueState(
        items: items,
        runner: state.runner,
        currentId: state.currentId,
      ),
    );
    await _persist();
    _kickIfLive();
  }

  /// Drop an item; the in-flight promote call can never be removed.
  Future<void> remove(String recordId) async {
    final QueueItem? item = state.byId(recordId);
    if (item == null ||
        item.status == QueueItemStatus.running ||
        _disposed) {
      return;
    }
    final List<QueueItem> items = List<QueueItem>.of(state.items)
      ..removeWhere((QueueItem queueItem) => queueItem.recordId == recordId);
    _commit(
      QueueState(
        items: items,
        runner: state.runner,
        currentId: state.currentId,
      ),
    );
    await _persist();
  }

  /// Drop every terminal line — status [QueueItemStatus.done] OR
  /// [QueueItemStatus.failed] — in one shot. Waiting and running items
  /// (and the in-flight [QueueState.currentId] record) are never touched.
  /// One `_commit` + one `_persist`, mirroring [remove]: persistence is
  /// mandatory or the cleared rows resurrect after a restart.
  Future<void> clearProcessed() async {
    if (_disposed) {
      return;
    }
    final List<QueueItem> items = List<QueueItem>.of(state.items)
      ..removeWhere(
        (QueueItem queueItem) =>
            queueItem.status == QueueItemStatus.done ||
            queueItem.status == QueueItemStatus.failed,
      );
    if (items.length == state.items.length) {
      return; // nothing terminal to clear — no commit, no write
    }
    _commit(
      QueueState(
        items: items,
        runner: state.runner,
        currentId: state.currentId,
      ),
    );
    await _persist();
  }

  /// Start (or resume) the runner: `running` when work waits, `waiting`
  /// when the queue is empty (the runner stays alive either way).
  Future<void> start() async {
    if (state.runner == QueueRunnerStatus.running || _disposed) {
      return;
    }
    _pauseRequested = false;
    final bool hasWork = state.waitingCount > 0;
    _commit(
      QueueState(
        items: state.items,
        runner: hasWork
            ? QueueRunnerStatus.running
            : QueueRunnerStatus.waiting,
        currentId: null,
      ),
    );
    await _persist();
    unawaited(_runLoop());
  }

  /// Ask the runner to stop after the CURRENT item (immediate when it is
  /// only waiting for one to appear).
  Future<void> pause() async {
    if (state.runner == QueueRunnerStatus.idle ||
        state.runner == QueueRunnerStatus.paused ||
        _disposed) {
      return;
    }
    _pauseRequested = true;
    _wake();
    _commit(
      QueueState(
        items: state.items,
        runner: QueueRunnerStatus.paused,
        currentId: state.currentId,
      ),
    );
    await _persist();
    // A sleeping/active loop clears `currentId` when it exits; without a
    // loop (restored snapshot) there is nothing left to clear.
    if (!_loopActive && state.currentId != null) {
      _commit(
        QueueState(
          items: state.items,
          runner: QueueRunnerStatus.paused,
          currentId: null,
        ),
      );
      await _persist();
    }
  }

  /// Wake/kick the drain loop when the runner is logically alive
  /// (`running` mid-item, `waiting` on an empty queue — including the
  /// restored-after-restart variant where no loop exists yet).
  void _kickIfLive() {
    if (state.runner == QueueRunnerStatus.running ||
        state.runner == QueueRunnerStatus.waiting) {
      _wake();
      unawaited(_runLoop());
    }
  }

  /// The sequential drain: first waiting item → promote → next; sleeps on
  /// an empty queue; exits on pause (item already finished).
  Future<void> _runLoop() async {
    if (_disposed || _loopActive) {
      return;
    }
    _loopActive = true;
    final QueueRepository repository = ref.read(queueRepositoryProvider);
    try {
      while (!_disposed) {
        if (_pauseRequested) {
          break;
        }
        final QueueItem? next = _firstWaiting();
        if (next == null) {
          // Empty while started → "waiting for next image" (stays alive).
          _commit(
            QueueState(
              items: state.items,
              runner: QueueRunnerStatus.waiting,
              currentId: null,
            ),
          );
          unawaited(_persist());
          await _sleep();
          continue;
        }
        _beginItem(next);
        try {
          await repository.promoteOne(next.recordId);
          if (!_disposed) {
            _finishItem(next.recordId, QueueItemStatus.done);
          }
        } catch (error) {
          if (!_disposed) {
            _finishItem(
              next.recordId,
              QueueItemStatus.failed,
              error: messageForQueueError(error),
            );
          }
          // Failure never stops the drain — the loop simply continues.
        }
      }
    } finally {
      _loopActive = false;
      if (!_disposed && _pauseRequested) {
        _commit(
          QueueState(
            items: state.items,
            runner: QueueRunnerStatus.paused,
            currentId: null,
          ),
        );
        await _persist();
      }
    }
  }

  QueueItem? _firstWaiting() {
    for (final QueueItem item in state.items) {
      if (item.status == QueueItemStatus.waiting) {
        return item;
      }
    }
    return null;
  }

  void _beginItem(QueueItem item) {
    final List<QueueItem> items = List<QueueItem>.of(state.items);
    final int at = items.indexWhere(
      (QueueItem queueItem) => queueItem.recordId == item.recordId,
    );
    items[at] = item.copyWith(
      status: QueueItemStatus.running,
      clearError: true,
    );
    _commit(
      QueueState(
        items: items,
        runner: QueueRunnerStatus.running,
        currentId: item.recordId,
      ),
    );
    unawaited(_persist());
  }

  void _finishItem(String recordId, QueueItemStatus status, {String? error}) {
    final List<QueueItem> items = List<QueueItem>.of(state.items);
    final int at = items.indexWhere(
      (QueueItem item) => item.recordId == recordId,
    );
    if (at >= 0) {
      items[at] = items[at].copyWith(
        status: status,
        error: error,
        clearError: error == null,
      );
    }
    _commit(
      QueueState(
        items: items,
        runner: state.runner,
        currentId: state.currentId == recordId ? null : state.currentId,
      ),
    );
    unawaited(_persist());
  }

  void _wake() {
    if (!_wakeup.isCompleted) {
      _wakeup.complete();
    }
  }

  /// Wait for the next [ _wake ] — a wake that arrived while an item was
  /// processing is consumed here (one extra spin) instead of being lost.
  Future<void> _sleep() async {
    if (!_wakeup.isCompleted) {
      await _wakeup.future;
    }
    _wakeup = Completer<void>();
  }

  void _commit(QueueState next) {
    if (!_disposed) {
      state = next;
    }
  }

  Future<void> _persist() async {
    if (_disposed) {
      return;
    }
    await _storage.save(state);
  }
}
