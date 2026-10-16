/// Gallery entity for one image record (05 §2.5) — the `RecordResponse`
/// shape from `backend/schemas.py` mapped to Dart.
///
/// Named **ImageRecord** because `Record` is a Dart 3 core type. The DTO
/// (`data/record_dto.dart`) owns JSON parsing; this class is a plain const
/// entity the detail screen and grid share.
class ImageRecord {
  const ImageRecord({
    required this.id,
    required this.filename,
    required this.status,
    this.originalPath,
    this.thumbnailPath,
    this.workingPath,
    this.stage,
    this.width,
    this.height,
    this.megapixels,
    this.fileSizeBytes,
    this.generatedTitle,
    this.generatedDescription,
    this.generatedKeywords,
    this.downloadName,
    this.suggestedFilename,
    this.uploadFilename,
    this.used,
    this.usedAt,
    this.acceptanceScore,
    this.category,
    this.groupId,
    this.batchId,
    this.promptId,
    this.createdAt,
    this.updatedAt,
    this.stageUpdatedAt,
  });

  final String id;
  final String filename;

  /// QC verdict: PENDING | AUDITING | PASSED | FLAGGED | APPROVED | READY.
  final String status;

  /// Absolute original path on the studio machine (basename is all clients
  /// may use — 02 §17).
  final String? originalPath;

  /// Absolute thumbnail path; [Thumbnail] reduces it to `{base}/thumbnails/…`.
  final String? thumbnailPath;

  /// Absolute path of the pipeline's latest output (cut-out, upscale) when
  /// a step has touched the file; null otherwise.
  final String? workingPath;

  /// Pipeline stage key (COLLECTED … PUBLISHED), when present.
  final String? stage;
  final int? width;
  final int? height;
  final double? megapixels;
  final int? fileSizeBytes;
  final String? generatedTitle;
  final String? generatedDescription;
  final List<String>? generatedKeywords;

  /// Operator delivery name / proposed + uploaded filenames (schemas.py).
  final String? downloadName;
  final String? suggestedFilename;
  final String? uploadFilename;

  /// Backend field is `is_used`; camelCase here per the entity contract.
  final bool? used;
  final DateTime? usedAt;
  final double? acceptanceScore;
  final int? category;
  final String? groupId;
  final String? batchId;
  final String? promptId;
  final DateTime? createdAt;
  final DateTime? updatedAt;
  final DateTime? stageUpdatedAt;

  /// Stamp tone source for the tile corner (05 §2.5 status stamp): approved/
  /// published → success, rejected/failed-ish → failure, default neutral.
  bool get isApproved => status == 'APPROVED' || status == 'READY';

  bool get isRejected =>
      status == 'FLAGGED' ||
      stage == 'OCR_REJECTED' ||
      stage == 'INCOMPATIBLE' ||
      stage == 'QUARANTINED';
}
