import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/utils/app_exception.dart';
import '../../../core/utils/ui_message.dart';
import '../../platforms/presentation/platforms_controller.dart';
import '../domain/batch.dart';
import '../domain/process_repository.dart';

/// Live transport state of one batch's detail screen (M4).
///
/// * [latest] — newest snapshot (SSE frame, or a polled `BatchDetail` while
///   falling back); null until the first payload lands.
/// * [live] — the SSE stream is flowing (`LiveDot 'LIVE'`).
/// * [pollingFallback] — SSE failed; the 2.5s `GET batches/{id}` loop is
///   running (`StatusChip 'POLLING'`).
/// * [error] — SSE **and** polling both failed; UI shows `ErrorView` + retry.
/// * [gone] — that failure was a 404 (backend restarted / batch deleted):
///   friendly wording + "back to list" (02 §16).
class BatchEventsState {
  const BatchEventsState({
    this.latest,
    this.live = false,
    this.pollingFallback = false,
    this.error,
    this.gone = false,
  });

  final BatchSnapshot? latest;
  final bool live;
  final bool pollingFallback;
  final String? error;
  final bool gone;
}

/// SSE-first live progress for `GET platformPath(id, 'batches/{id}/events')`
/// with an automatic polling fallback (05 §2.7.2 "prefer SSE … fall back …
/// automatically").
///
/// State machine: [build] opens the stream → frames set [live] → any stream
/// error (including the 404 probed before the stream opens) starts the 2.5s
/// poll loop ([pollingFallback]) → the first poll failure lands in [error].
/// A stream that closes without `event: done` while the batch is still not
/// terminal (proxy cut) also falls back to polling. Terminal snapshots stop
/// the loop. Dispose cancels both the Dio stream (CancelToken) and the timer
/// (03 §4 lifecycle).
final batchEventsProvider = NotifierProvider.autoDispose
    .family<BatchEventsController, BatchEventsState, String>(
  BatchEventsController.new,
);

class BatchEventsController extends Notifier<BatchEventsState> {
  BatchEventsController(this.batchId);

  /// The batch being watched (matches `batchDetailProvider`'s arg).
  final String batchId;

  StreamSubscription<BatchSnapshot>? _live;
  Timer? _poll;
  bool _pollInFlight = false;
  bool _disposed = false;

  /// Bumped whenever polling stops so an in-flight request from the old
  /// generation can't write state after a retry/teardown.
  int _epoch = 0;

  ProcessRepository get _repository => ref.read(processRepositoryProvider);

  @override
  BatchEventsState build() {
    ref.watch(activePlatformIdProvider);
    ref.onDispose(_teardown);
    _startLive();
    return const BatchEventsState();
  }

  /// ErrorView retry: tear everything down and try SSE afresh.
  void retry() {
    if (_disposed) {
      return;
    }
    _stopPolling();
    final StreamSubscription<BatchSnapshot>? live = _live;
    _live = null;
    unawaited(live?.cancel());
    state = const BatchEventsState();
    _startLive();
  }

  void _startLive() {
    StreamSubscription<BatchSnapshot>? sub;
    sub = _repository.watchBatch(batchId).listen(
      (BatchSnapshot snapshot) {
        if (_disposed) {
          return;
        }
        state = BatchEventsState(latest: snapshot, live: true);
      },
      onError: (Object error) {
        // Immediate (or mid-run) stream failure → automatic fallback (05 §2.7.2).
        if (_disposed) {
          return;
        }
        _live = null;
        _startPolling();
      },
      onDone: () {
        if (_disposed) {
          return;
        }
        _live = null;
        final bool finished = state.latest?.batch.isTerminal ?? false;
        if (!finished) {
          // Closed without `event: done` (cut connection) — keep polling.
          _startPolling();
        }
      },
      cancelOnError: true,
    );
    _live = sub;
  }

  void _startPolling() {
    if (_disposed || _poll != null) {
      return;
    }
    state = BatchEventsState(latest: state.latest, pollingFallback: true);
    // First poll runs immediately (fast fallback); the timer handles cadence.
    unawaited(_pollOnce());
    _poll = Timer.periodic(
      const Duration(milliseconds: 2500),
      (Timer timer) => unawaited(_pollOnce()),
    );
  }

  void _stopPolling() {
    _poll?.cancel();
    _poll = null;
    _pollInFlight = false;
    _epoch++;
  }

  Future<void> _pollOnce() async {
    final int epoch = _epoch;
    if (_pollInFlight || _disposed) {
      return;
    }
    _pollInFlight = true;
    try {
      final BatchDetail detail = await _repository.fetchBatchDetail(batchId);
      _pollInFlight = false;
      if (_disposed || epoch != _epoch) {
        return;
      }
      if (detail.isTerminal) {
        _stopPolling();
        state = BatchEventsState(latest: BatchSnapshot(detail));
      } else {
        state = BatchEventsState(
          latest: BatchSnapshot(detail),
          pollingFallback: true,
        );
      }
    } catch (error) {
      _pollInFlight = false;
      if (_disposed || epoch != _epoch) {
        return;
      }
      _stopPolling();
      state = BatchEventsState(
        latest: state.latest,
        error: _errorMessage(error),
        gone: error is NotFoundException,
      );
    }
  }

  void _teardown() {
    _disposed = true;
    _stopPolling();
    final StreamSubscription<BatchSnapshot>? live = _live;
    _live = null;
    unawaited(live?.cancel());
  }

  static String _errorMessage(Object error) {
    if (error is NotFoundException) {
      // 02 §16: studio restarted mid-screen, the batch id no longer exists.
      return 'Batch info no longer available (studio restarted)';
    }
    if (error is AppException) {
      return uiMessageFor(error);
    }
    return 'Something went wrong.';
  }
}
