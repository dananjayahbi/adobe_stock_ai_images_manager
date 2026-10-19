/// Gallery entity for one image record (05 §2.5) — the `RecordResponse`
/// shape from `backend/schemas.py` mapped to Dart.
///
/// Named **ImageRecord** because `Record` is a Dart 3 core type. The DTO
/// (`data/record_dto.dart`) owns JSON parsing; this class is a plain const
/// entity the detail screen and grid share.
///
/// Every record carries exactly one **state** (its lifecycle position) and
/// an ordered list of **flags**; the legacy `status`/`stage`/`is_used`
/// fields remain for pipeline screens and older payloads.
library;

/// All image states in lifecycle order — the `state` contract
/// (`COLLECTED → APPROVED/REJECTED → READY_TO_PUBLISH → PUBLISHED ⇄
/// AS_ACCEPTED`). Plain Dart so `domain/` stays framework-free; labels and
/// tones live in `presentation/image_state_presentation.dart`.
const List<String> kImageStates = <String>[
  'COLLECTED',
  'APPROVED',
  'REJECTED',
  'READY_TO_PUBLISH',
  'PUBLISHED',
  'AS_ACCEPTED',
];

/// All image flags in the contract's **display order**. Exactly one of
/// `USED`/`UNUSED` is always present on new payloads; older payloads may
/// carry none.
const List<String> kImageFlags = <String>[
  'QUARANTINED',
  'USED',
  'UNUSED',
  'METADATA_READY',
  'INCOMPATIBLE',
  'REFINED',
  'UPSCALED',
  'OCR_REJECTED',
];

class ImageRecord {
  const ImageRecord({
    required this.id,
    required this.filename,
    required this.status,
    this.state = 'COLLECTED',
    this.flags = const <String>[],
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
    bool? used,
    this.usedAt,
    this.acceptanceScore,
    this.category,
    this.groupId,
    this.batchId,
    this.promptId,
    this.createdAt,
    this.updatedAt,
    this.stageUpdatedAt,
  }) : _isUsed = used;

  final String id;
  final String filename;

  /// QC verdict: PENDING | AUDITING | PASSED | FLAGGED | APPROVED | READY.
  final String status;

  /// Lifecycle state — one of [kImageStates]; defaulted for fixtures and
  /// entity-level construction (the DTO resolves legacy payloads).
  final String state;

  /// Flags from [kImageFlags], already in display order; empty until the
  /// backend ships them (legacy payloads).
  final List<String> flags;

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

  /// Backend field is `is_used`; kept as the fallback for payloads whose
  /// `flags` do not carry the used complement (see [used]).
  final bool? _isUsed;
  final DateTime? usedAt;
  final double? acceptanceScore;
  final int? category;
  final String? groupId;
  final String? batchId;
  final String? promptId;
  final DateTime? createdAt;
  final DateTime? updatedAt;
  final DateTime? stageUpdatedAt;

  /// Whether the record is consumed: the `flags` complement wins (USED ⇒
  /// true, UNUSED ⇒ false), falling back to the legacy `is_used` field.
  bool? get used {
    if (flags.contains('USED')) {
      return true;
    }
    if (flags.contains('UNUSED')) {
      return false;
    }
    return _isUsed;
  }

  /// Pipeline passed (state lens; legacy getter name kept — widely used).
  bool get isApproved => state == 'APPROVED';

  /// Pipeline failed (state lens; legacy getter name kept).
  bool get isRejected => state == 'REJECTED';

  bool get isReadyToPublish => state == 'READY_TO_PUBLISH';

  bool get isPublished => state == 'PUBLISHED';

  bool get isAsAccepted => state == 'AS_ACCEPTED';

  /// The only states the Approve action may flip (→ READY_TO_PUBLISH).
  bool get isApprovable => isApproved || isRejected;

  /// The only state publish-now applies to.
  bool get canPublishNow => isReadyToPublish;
}
