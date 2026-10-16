/// Domain models for the Delivery screen (05 §2.8): what can be delivered,
/// what a CSV preview said, what an action saved, and what force-accept /
/// rename reported back (02 §7).
///
/// Shapes mirror the live payloads captured from `POST /api/assets/*` on the
/// running studio server — see `backend/routers/delivery.py` and
/// `backend/schemas.py` for the server-side truth.
library;

/// Stage filter chips over the delivery list (05: "selected stage filter
/// chips"). Filtering is client-side: one `GET /api/records` snapshot keeps
/// chip taps instant (02 §16 gap 2 — no light payload yet).
enum DeliveryFilter {
  all('ALL'),
  deliverable('DELIVERABLE'),
  forceable('FORCEABLE');

  const DeliveryFilter(this.label);

  /// Chip caption — StatusChip renders it as-is (uppercase by convention).
  final String label;

  /// Whether [candidate] belongs under this chip.
  bool accepts(DeliveryCandidate candidate) => switch (this) {
        DeliveryFilter.all => true,
        DeliveryFilter.deliverable => candidate.deliverable,
        DeliveryFilter.forceable => candidate.forceable,
      };
}

/// One record row in the delivery list — the id-bearing selection source
/// for ZIP bundle / force-accept (02 §7 requires explicit `record_ids`).
class DeliveryCandidate {
  const DeliveryCandidate({
    required this.id,
    required this.filename,
    required this.stage,
    this.uploadFilename,
    this.title,
    this.isUsed = false,
  });

  final String id;

  /// Original filename as uploaded.
  final String filename;

  /// `PipelineStage` value string, e.g. `METADATA_READY`.
  final String stage;

  /// Server-resolved delivery name (`RecordResponse.upload_filename`) — the
  /// string the CSV, download and ZIP entry all agree on.
  final String? uploadFilename;

  final String? title;
  final bool isUsed;

  /// The name that will actually ship (upload filename, else original).
  String get effectiveName =>
      (uploadFilename != null && uploadFilename!.isNotEmpty)
          ? uploadFilename!
          : filename;

  /// Uploadable now — `only_ready` on the server is exactly these stages
  /// (`stage_orchestrator.build_metadata_csv`).
  bool get deliverable =>
      stage == 'METADATA_READY' || stage == 'PUBLISHED';

  /// Whether `POST /api/assets/force-accept` can advance this record
  /// (`forced_acceptance.can_force`): gate-failed or earlier stages only —
  /// OCR rejections and already-accepted rows are refused server-side.
  bool get forceable => switch (stage) {
        'INCOMPATIBLE' ||
        'COLLECTED' ||
        'OCR_CLEAR' ||
        'UPSCALED' ||
        'REFINED' =>
          true,
        _ => false,
      };
}

/// `POST /api/assets/csv/preview` response — CSV text plus notes, no side
/// effects (`apply_names` stays off for a preview).
class CsvPreview {
  const CsvPreview({
    required this.csvText,
    required this.rowCount,
    this.skipped = const <String>[],
    this.warnings = const <String>[],
  });

  final String csvText;
  final int rowCount;

  /// Record ids the server could not represent in a row.
  final List<String> skipped;

  /// Non-fatal notes, e.g. a title that had to be truncated.
  final List<String> warnings;

  /// `csv_text` split into physical lines (CRLF-tolerant), header included;
  /// the trailing newline every export ends with does not add a phantom row.
  List<String> get lines {
    if (csvText.isEmpty) return const <String>[];
    final List<String> parts = csvText.split(RegExp(r'\r?\n'));
    if (parts.isNotEmpty && parts.last.isEmpty) {
      parts.removeLast();
    }
    return parts;
  }
}

/// A byte download with its server-suggested filename
/// (`Content-Disposition: attachment; filename="…"`).
class DeliveryFile {
  const DeliveryFile({required this.fileName, required this.bytes});

  final String fileName;
  final List<int> bytes;
}

/// What a finished export was (`05` history: caption + stamp status).
enum ExportKind {
  csv('CSV'),
  zip('ZIP');

  const ExportKind(this.label);
  final String label;
}

/// One saved export for the session-local "recent exports" history.
class ExportRecord {
  const ExportRecord({
    required this.fileName,
    required this.savedPath,
    required this.byteCount,
    required this.kind,
    required this.exportedAt,
  });

  final String fileName;
  final String savedPath;
  final int byteCount;
  final ExportKind kind;
  final DateTime exportedAt;
}

/// Per-record outcome inside a force-accept response
/// (`ForcedAcceptResultItem` — refused rows keep an explanation reason).
class ForceAcceptItem {
  const ForceAcceptItem({
    required this.recordId,
    required this.accepted,
    required this.previousStage,
    this.newStage,
    this.score,
    this.reason = '',
  });

  final String recordId;
  final bool accepted;
  final String previousStage;
  final String? newStage;
  final double? score;
  final String reason;
}

/// `POST /api/assets/force-accept` response (02 §7): counts drive the
/// result toast, items carry the per-record reasons.
class ForceAcceptOutcome {
  const ForceAcceptOutcome({
    required this.items,
    required this.accepted,
    required this.refused,
  });

  final List<ForceAcceptItem> items;
  final int accepted;
  final int refused;
}

/// One row of a rename response (`RenameResultItem`).
class RenameResultItem {
  const RenameResultItem({
    required this.recordId,
    required this.filename,
    this.downloadName,
    this.changed = false,
    this.error,
  });

  final String recordId;
  final String filename;
  final String? downloadName;
  final bool changed;
  final String? error;
}

/// `RenameResponse` from rename / rename-suggest / apply-suggested-names.
class RenameOutcome {
  const RenameOutcome({
    required this.items,
    required this.updated,
    required this.failed,
  });

  final List<RenameResultItem> items;
  final int updated;
  final int failed;
}

/// One entry of a rename request (`RenameItemRequest`).
class RenameEntry {
  const RenameEntry({required this.recordId, required this.name});

  final String recordId;
  final String name;
}
