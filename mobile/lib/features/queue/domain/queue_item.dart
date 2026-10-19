/// Readiness-queue domain (R3) — plain entities, no framework imports.
///
/// The queue holds records waiting for the promote check/run pass that
/// fills per-record gaps (metadata, sRGB embed, …). One app-level runner
/// drains it sequentially; persistence serialises these types to JSON
/// (`data/queue_repository.dart` owns the storage key + codec).
library;

/// Lifecycle of one queued record.
enum QueueItemStatus {
  /// Queued; picked up next time the runner reaches it.
  waiting,

  /// The promote call for this record is in flight right now.
  running,

  /// Promote finished successfully (gaps filled / record moved on).
  done,

  /// Promote failed — [QueueItem.error] carries the reason; retryable.
  failed,
}

/// Runner state (mutually exclusive with "nothing queued yet"):
///
/// * [idle] — never started this session; items accumulate until Start.
/// * [running] — draining the deque one record at a time.
/// * [paused] — stopped after the CURRENT item finished (Start resumes).
/// * [waiting] — started with an empty queue ("waiting for next image"):
///   the runner stays logically alive, so the next enqueue is picked up
///   without pressing Start again.
enum QueueRunnerStatus { idle, running, paused, waiting }

/// One record in the deque: identity + presentation status.
class QueueItem {
  const QueueItem({
    required this.recordId,
    required this.filename,
    this.status = QueueItemStatus.waiting,
    this.error,
  });

  /// Gallery record id — the promote call's `record_ids` entry.
  final String recordId;

  /// Display name (grid filename); may be empty when enqueued blind.
  final String filename;

  final QueueItemStatus status;

  /// Failure reason for [QueueItemStatus.failed] (backend `detail` when
  /// the promote API supplied one).
  final String? error;

  QueueItem copyWith({
    String? filename,
    QueueItemStatus? status,
    String? error,
    bool clearError = false,
  }) => QueueItem(
        recordId: recordId,
        filename: filename ?? this.filename,
        status: status ?? this.status,
        error: clearError ? null : error ?? this.error,
      );

  Map<String, dynamic> toJson() => <String, dynamic>{
        'record_id': recordId,
        'filename': filename,
        'status': status.name,
        if (error != null) 'error': error,
      };

  factory QueueItem.fromJson(Map<String, dynamic> json) => QueueItem(
        recordId: json['record_id'] as String? ?? '',
        filename: json['filename'] as String? ?? '',
        status: queueItemStatusByName(json['status'] as String?),
        error: json['error'] as String?,
      );
}

/// Unknown JSON status strings degrade to [QueueItemStatus.waiting] so a
/// newer build's payload never crashes an older restore path.
QueueItemStatus queueItemStatusByName(String? name) =>
    QueueItemStatus.values.firstWhere(
      (QueueItemStatus value) => value.name == name,
      orElse: () => QueueItemStatus.waiting,
    );

/// Unknown JSON runner strings degrade to [QueueRunnerStatus.idle].
QueueRunnerStatus queueRunnerStatusByName(String? name) =>
    QueueRunnerStatus.values.firstWhere(
      (QueueRunnerStatus value) => value.name == name,
      orElse: () => QueueRunnerStatus.idle,
    );
