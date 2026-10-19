import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../core/utils/app_exception.dart';
import '../../platforms/presentation/platforms_controller.dart';
import '../domain/queue_item.dart';
import '../domain/queue_state.dart';
import 'promote_api.dart';

/// Single seam the queue tests override to fake promote work (the runner
/// tests care about sequencing, not HTTP).
abstract class QueueRepository {
  /// `promote/check` → `promote/run` → poll `jobs/{id}` for ONE record;
  /// throws with the backend's reason when the record is blocked or the
  /// job line ends `failed`/`skipped`.
  Future<void> promoteOne(String recordId);
}

/// Wired to the shared Dio client (CookieManager replays the session) and
/// the active platform id, mirroring `galleryRepositoryProvider`.
final queueRepositoryProvider = Provider<QueueRepository>((ref) {
  final String platformId = ref.watch(activePlatformIdProvider);
  return PromoteQueueRepository(
    api: ref.watch(promoteApiProvider),
    platformId: platformId,
  );
});

/// Real implementation: check (pre-flight) → run (background job) → poll.
///
/// [pollInterval] and [maxPolls] bound the wait (default ≈10 min — stage
/// jobs are second-scale; a stuck `running` job must not wedge the queue).
class PromoteQueueRepository implements QueueRepository {
  PromoteQueueRepository({
    required this.api,
    required this.platformId,
    this.pollInterval = const Duration(milliseconds: 400),
    this.maxPolls = 1500,
  });

  final PromoteApi api;
  final String platformId;
  final Duration pollInterval;
  final int maxPolls;

  @override
  Future<void> promoteOne(String recordId) async {
    final PromoteCheckResult check = await api.check(
      platformId,
      <String>[recordId],
    );
    if (check.missing.contains(recordId) && check.itemFor(recordId) == null) {
      throw const NotFoundException(message: 'This record no longer exists.');
    }
    final PromoteCheckItem? preflight = check.itemFor(recordId);
    if (preflight != null && !preflight.eligible) {
      throw ValidationException(
        message: preflight.blocker ?? 'This record is not eligible.',
      );
    }

    final PromoteJob job = await api.run(platformId, <String>[recordId]);
    if (job.id.isEmpty) {
      throw const ServerException(message: 'Promote job did not start.');
    }
    PromoteJob snapshot = job;
    for (int polls = 0; snapshot.isRunning; polls++) {
      if (polls >= maxPolls) {
        throw const ServerException(message: 'Promote job timed out.');
      }
      await Future<void>.delayed(pollInterval);
      snapshot = await api.job(platformId, job.id);
    }

    final PromoteJobItem? line = snapshot.itemFor(recordId);
    if (line == null) {
      throw const ServerException(message: 'Promote returned no result.');
    }
    switch (line.status) {
      case 'succeeded':
        return;
      case 'skipped':
        // Orchestrator refusal path: blocked record or cancelled job.
        throw ValidationException(
          message: line.message.isEmpty ? 'Promote skipped this record.' : line.message,
        );
      default:
        throw ServerException(
          message: line.message.isEmpty ? 'Promote failed.' : line.message,
        );
    }
  }
}

/// Human text for a queue failure line: backend `detail` verbatim when
/// present, generic copy otherwise (same contract as `uiMessageFor`).
String messageForQueueError(Object error) {
  if (error is AppException && (error.message?.isNotEmpty ?? false)) {
    return error.message!;
  }
  if (error is Exception) {
    final String text = error.toString();
    if (text.isNotEmpty) {
      return text;
    }
  }
  return 'Something went wrong.';
}

/// SharedPreferences snapshot for the deque (R3): JSON under
/// [kQueueStorageKey] so a restart restores waiting items.
///
/// Restore mapping (documented restart policy):
/// * item `running` → `waiting` (its promote call died with the process);
/// * runner `running` → `paused` (nothing resumes without Start),
///   `waiting` stays `waiting` when the queue is empty (the next enqueue
///   auto-picks up), or drops to `paused` if items were left behind;
/// * `current_id` never survives — no job survives the restart.
class QueueStorage {
  QueueStorage(this._prefs);

  static const String kQueueStorageKey = 'readiness_queue_v1';
  static const int kVersion = 1;

  final SharedPreferences _prefs;

  QueueState load() {
    final String? raw = _prefs.getString(kQueueStorageKey);
    if (raw == null || raw.isEmpty) {
      return const QueueState();
    }
    return decodeQueueSnapshot(raw);
  }

  Future<void> save(QueueState state) =>
      _prefs.setString(kQueueStorageKey, encodeQueueSnapshot(state));
}

/// JSON codec — top-level so tests can round-trip without a storage seam.
const int kQueueSnapshotVersion = 1;

String encodeQueueSnapshot(QueueState state) => jsonEncode(<String, dynamic>{
      'version': kQueueSnapshotVersion,
      'runner': state.runner.name,
      'items': state.items
          .map((QueueItem item) => item.toJson())
          .toList(growable: false),
    });

QueueState decodeQueueSnapshot(String raw) {
  try {
    final Object? decoded = jsonDecode(raw);
    if (decoded is! Map<String, dynamic>) {
      return const QueueState();
    }
    final List<QueueItem> items =
        ((decoded['items'] as List<dynamic>? ?? <dynamic>[])
                .whereType<Map<String, dynamic>>())
            .map(QueueItem.fromJson)
            .toList(growable: false);
    final List<QueueItem> restored = items
        .map((QueueItem item) => item.status == QueueItemStatus.running
            ? item.copyWith(status: QueueItemStatus.waiting, clearError: true)
            : item)
        .toList(growable: false);
    final bool anyWaiting = restored
        .any((QueueItem item) => item.status == QueueItemStatus.waiting);
    final QueueRunnerStatus persisted =
        queueRunnerStatusByName(decoded['runner'] as String?);
    final QueueRunnerStatus runner = switch (persisted) {
      QueueRunnerStatus.running => QueueRunnerStatus.paused,
      QueueRunnerStatus.waiting =>
        anyWaiting ? QueueRunnerStatus.paused : QueueRunnerStatus.waiting,
      _ => persisted,
    };
    return QueueState(items: restored, runner: runner);
  } on FormatException {
    return const QueueState();
  }
}
