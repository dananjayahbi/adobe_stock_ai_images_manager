import 'batch_step.dart';

/// Batch pipeline entities — the client mirrors of the backend models in
/// `backend/routers/batches.py` (02 §6). Field docs name the exact JSON key
/// each member parses; Dart keeps the codebase's camelCase convention
/// (same approach as gallery's `RecordDto`).
///
/// Model map:
/// * [Batch] ← `BatchResponse` (`GET/POST /api/batches`, `GET …/{id}` sans
///   records, `POST …/run|cancel`, and every SSE `data:` frame).
/// * [BatchDetail] ← `BatchDetailResponse` (`GET /api/batches/{id}` — a
///   `BatchResponse` plus `records: RecordResponse[]`).
/// * [BatchList] ← `BatchListResponse {items, total}`.
/// * [BatchSnapshot] ← one decoded SSE frame (contract of
///   `BatchEventsClient.watchBatch`).
///
/// Backend status vocabulary (models.py `BatchStatus` — 02 §6's
/// `pending|succeeded` wording is stale, backend wins): `draft`, `queued`,
/// `running`, `completed`, `failed`, `cancelled`.
class Batch {
  const Batch({
    required this.id,
    required this.name,
    required this.mediaType,
    required this.steps,
    required this.profileId,
    required this.status,
    required this.stepProgress,
    required this.error,
    required this.recordCount,
    required this.createdAt,
    required this.updatedAt,
    required this.finishedAt,
    this.queuedAt,
  });

  /// Defensive parse of one `BatchResponse` object: missing fields fall back
  /// to neutral defaults so one odd row never breaks a page (M2 contract);
  /// a wrong *container* is the repository's job to reject.
  factory Batch.fromJson(Map<String, Object?> json) {
    return Batch(
      id: _text(json['id']),
      name: _text(json['name']),
      mediaType: _text(json['media_type']) == 'png' ? 'png' : 'raster',
      steps: _steps(json['steps']),
      profileId: _textOrNull(json['profile_id']),
      // Backend emits draft|queued|running|completed|failed|cancelled;
      // anything unknown renders as draft rather than crashing a card.
      status: _status(json['status']),
      stepProgress: _stepProgress(json['step_progress']),
      error: _textOrNull(json['error']),
      recordCount: _int(json['record_count']),
      createdAt: _dateTime(json['created_at']),
      updatedAt: _dateTime(json['updated_at']),
      finishedAt: _dateTime(json['finished_at']),
      queuedAt: _dateTime(json['queued_at']),
    );
  }

  /// `id`.
  final String id;

  /// `name`.
  final String name;

  /// `media_type` — `raster` | `png` (anything else normalises to raster).
  final String mediaType;

  /// `steps` — ordered `[{key, config}]` (see [BatchStep]).
  final List<BatchStep> steps;

  /// `profile_id` — the step profile this batch was seeded from, if any.
  final String? profileId;

  /// `status` — `draft|queued|running|completed|failed|cancelled`.
  final String status;

  /// `step_progress` — `{step_key: {status, message, counts}} | null`,
  /// written live by the pipeline runner (see [StepProgress]).
  final Map<String, StepProgress>? stepProgress;

  /// `error` — set when `status == failed` (which step and why).
  final String? error;

  /// `record_count` — images currently inside the batch.
  final int recordCount;

  /// `created_at` (ISO-8601).
  final DateTime? createdAt;

  /// `updated_at` (ISO-8601).
  final DateTime? updatedAt;

  /// `finished_at` (ISO-8601) — null until a run ends.
  final DateTime? finishedAt;

  /// `queued_at` (ISO-8601 | null) — set when the batch was enqueued;
  /// drives the queue's FIFO ordering (M4 contract).
  final DateTime? queuedAt;

  bool get isRunning => status == 'running';

  /// Enqueued, waiting for a runner slot.
  bool get isQueued => status == 'queued';

  /// On the board right now — running or queued (list polling + detail
  /// actions treat these alike).
  bool get isActive => status == 'running' || status == 'queued';

  /// Terminal per backend `_BATCH_TERMINAL_STATUSES`.
  bool get isTerminal =>
      status == 'completed' || status == 'failed' || status == 'cancelled';

  /// Overall run progress in 0..1 for the header/card ProgressBar, computed
  /// from `step_progress` — `BatchResponse` carries **no** `progress` field
  /// (unlike `JobResponse.progress`), so the client derives it: finished
  /// steps count 1, a running step contributes its processed fraction
  /// (`(succeeded+failed+skipped) / counts total`), pending steps 0.
  /// Returns null when progress is unknowable (draft, or a running batch
  /// whose `step_progress` has not landed yet) → indeterminate bar.
  double? get progress {
    if (steps.isEmpty) {
      return null;
    }
    if (status == 'completed') {
      return 1.0;
    }
    final Map<String, StepProgress>? live = stepProgress;
    if (live == null) {
      return null;
    }
    double done = 0.0;
    for (final BatchStep step in steps) {
      final StepProgress? stepState = live[step.key];
      if (stepState == null) {
        continue;
      }
      switch (stepState.status) {
        case 'completed':
        case 'failed':
        case 'cancelled':
          done += 1;
        case 'running':
          done += _stepFraction(stepState.counts);
        default:
          break; // pending / unknown → 0
      }
    }
    return (done / steps.length).clamp(0.0, 1.0);
  }

  /// Processed fraction inside one running step from its counts snapshot.
  static double _stepFraction(Map<String, int>? counts) {
    if (counts == null || counts.isEmpty) {
      return 0.0;
    }
    int total = 0;
    for (final int value in counts.values) {
      total += value;
    }
    if (total == 0) {
      return 0.0;
    }
    final int pending = (counts['pending'] ?? 0) + (counts['running'] ?? 0);
    final int processed = total - pending;
    return (processed / total).clamp(0.0, 1.0);
  }

  static String _status(Object? value) {
    const Set<String> known = <String>{
      'draft',
      'queued',
      'running',
      'completed',
      'failed',
      'cancelled',
    };
    final String text = value?.toString() ?? '';
    return known.contains(text) ? text : 'draft';
  }

  static List<BatchStep> _steps(Object? value) {
    if (value is! List<Object?>) {
      return const <BatchStep>[];
    }
    final List<BatchStep> steps = <BatchStep>[];
    for (final Object? row in value) {
      if (row is Map<Object?, Object?>) {
        steps.add(BatchStep.fromJson(_stringKeyed(row)));
      }
    }
    return steps;
  }

  static Map<String, StepProgress>? _stepProgress(Object? value) {
    if (value is! Map<Object?, Object?>) {
      return null;
    }
    final Map<String, StepProgress> parsed = <String, StepProgress>{};
    for (final MapEntry<Object?, Object?> entry in value.entries) {
      final Object? key = entry.key;
      final Object? rawState = entry.value;
      if (key is! String || rawState is! Map<Object?, Object?>) {
        continue;
      }
      parsed[key] = StepProgress.fromJson(_stringKeyed(rawState));
    }
    return parsed;
  }

  static Map<String, Object?> _stringKeyed(Map<Object?, Object?> map) =>
      map.map<String, Object?>(
        (Object? key, Object? value) =>
            MapEntry<String, Object?>(key?.toString() ?? '', value),
      );

  static String _text(Object? value) => value?.toString() ?? '';

  static String? _textOrNull(Object? value) =>
      value is String && value.isNotEmpty ? value : null;

  static int _int(Object? value) => value is num ? value.toInt() : 0;

  static DateTime? _dateTime(Object? value) =>
      value is String ? DateTime.tryParse(value) : null;
}

/// `BatchDetailResponse` — `BatchResponse` + `records: RecordResponse[]`
/// (`GET /api/batches/{id}`, the poll target of the fallback loop).
class BatchDetail extends Batch {
  const BatchDetail({
    required super.id,
    required super.name,
    required super.mediaType,
    required super.steps,
    required super.profileId,
    required super.status,
    required super.stepProgress,
    required super.error,
    required super.recordCount,
    required super.createdAt,
    required super.updatedAt,
    required super.finishedAt,
    super.queuedAt,
    required this.records,
  });

  factory BatchDetail.fromJson(Map<String, Object?> json) {
    final Batch batch = Batch.fromJson(json);
    final List<BatchRecord> records = <BatchRecord>[];
    final Object? rows = json['records'];
    if (rows is List<Object?>) {
      for (final Object? row in rows) {
        if (row is Map<Object?, Object?>) {
          records.add(
            BatchRecord.fromJson(
              row.map<String, Object?>(
                (Object? key, Object? value) =>
                    MapEntry<String, Object?>(key?.toString() ?? '', value),
              ),
            ),
          );
        }
      }
    }
    return BatchDetail(
      id: batch.id,
      name: batch.name,
      mediaType: batch.mediaType,
      steps: batch.steps,
      profileId: batch.profileId,
      status: batch.status,
      stepProgress: batch.stepProgress,
      error: batch.error,
      // A payload missing the counter falls back to the parsed rows so the
      // header never claims 0 images while the grid shows some.
      recordCount: json['record_count'] is num
          ? (json['record_count'] as num).toInt()
          : records.length,
      createdAt: batch.createdAt,
      updatedAt: batch.updatedAt,
      finishedAt: batch.finishedAt,
      queuedAt: batch.queuedAt,
      records: records,
    );
  }

  /// `records` — the batch's images (subset of `RecordResponse` fields the
  /// results grid needs; see [BatchRecord]).
  final List<BatchRecord> records;
}

/// One `RecordResponse` row inside `BatchDetailResponse.records`, trimmed to
/// what the results grid renders (full metadata lives in gallery's
/// `ImageRecord`).
class BatchRecord {
  const BatchRecord({
    required this.id,
    required this.filename,
    required this.thumbnailPath,
    required this.stage,
    required this.status,
  });

  factory BatchRecord.fromJson(Map<String, Object?> json) => BatchRecord(
    id: json['id']?.toString() ?? '',
    filename: json['filename']?.toString() ?? '',
    thumbnailPath: json['thumbnail_path'] is String
        ? json['thumbnail_path']! as String
        : null,
    stage: json['stage'] is String ? json['stage']! as String : null,
    status: json['status']?.toString() ?? '',
  );

  /// `id`.
  final String id;

  /// `filename`.
  final String filename;

  /// `thumbnail_path` (absolute studio path; `Thumbnail` derives the URL).
  final String? thumbnailPath;

  /// `stage` — pipeline stage stamp for the tile.
  final String? stage;

  /// `status` — audit lifecycle (`PENDING…APPROVED`).
  final String status;
}

/// `BatchListResponse {items: [BatchResponse], total}` —
/// `GET /api/batches?limit=…` (newest first).
class BatchList {
  const BatchList({required this.items, required this.total});

  factory BatchList.fromJson(Map<String, Object?> json) {
    final List<Batch> items = <Batch>[];
    final Object? rows = json['items'];
    if (rows is List<Object?>) {
      for (final Object? row in rows) {
        if (row is Map<Object?, Object?>) {
          items.add(
            Batch.fromJson(
              row.map<String, Object?>(
                (Object? key, Object? value) =>
                    MapEntry<String, Object?>(key?.toString() ?? '', value),
              ),
            ),
          );
        }
      }
    }
    return BatchList(
      items: items,
      total: json['total'] is num
          ? (json['total']! as num).toInt()
          : items.length,
    );
  }

  /// `items`.
  final List<Batch> items;

  /// `total` — full count on the server (may exceed `items.length`).
  final int total;
}

/// One decoded SSE frame from `GET /api/batches/{id}/events` — the payload
/// of `BatchEventsClient.watchBatch` (02 §11: frames are `data:{json}` of
/// the `BatchResponse` shape; `event: done` closes the stream).
class BatchSnapshot {
  const BatchSnapshot(this.batch);

  /// The `BatchResponse` this frame carried.
  final Batch batch;
}
