import 'queue_item.dart';

/// Immutable snapshot the UI renders: the deque, the runner state and the
/// record id currently being promoted (null unless the runner is draining).
class QueueState {
  const QueueState({
    this.items = const <QueueItem>[],
    this.runner = QueueRunnerStatus.idle,
    this.currentId,
  });

  /// Deque in queue order (waiting · running · done · failed mixed; the
  /// runner always picks the first [QueueItemStatus.waiting]).
  final List<QueueItem> items;

  final QueueRunnerStatus runner;

  /// Record id of the in-flight promote call.
  final String? currentId;

  /// Items still ahead of the runner — the count the indicator leads with.
  int get waitingCount => items
      .where((QueueItem item) => item.status == QueueItemStatus.waiting)
      .length;

  bool get isEmpty => items.isEmpty;

  /// Visible work: anything queued, or a live runner — `running` /
  /// `waiting` (a `waiting` runner must stay legible: the next approval
  /// auto-picks up). A `paused` runner with an EMPTY deque hides the bar
  /// (nothing to resume); paused with items stays visible (R3 decision).
  bool get isVisible =>
      items.isNotEmpty ||
      runner == QueueRunnerStatus.running ||
      runner == QueueRunnerStatus.waiting;

  QueueItem? byId(String recordId) {
    for (final QueueItem item in items) {
      if (item.recordId == recordId) {
        return item;
      }
    }
    return null;
  }
}
