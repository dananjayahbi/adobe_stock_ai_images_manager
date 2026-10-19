import '../domain/image_record.dart';

/// JSON → [ImageRecord] mapping for one `RecordResponse` row (02 §3).
///
/// Parsing follows the M2 defensive contract: a missing *field* falls back
/// to null/empty defaults so one odd row never fails a whole page; a wrong
/// *container* (HTML error page, `null` body) is the repository's job to
/// reject with [ServerException].
class RecordDto {
  const RecordDto(this.json);

  /// Raw row from `items[]`, string-keyed.
  final Map<String, Object?> json;

  ImageRecord toEntity() {
    return ImageRecord(
      id: _text(json['id']),
      filename: _text(json['filename']),
      status: _text(json['status']),
      state: _state(),
      flags: _flags(),
      originalPath: _textOrNull(json['original_path']),
      thumbnailPath: _textOrNull(json['thumbnail_path']),
      workingPath: _textOrNull(json['working_path']),
      stage: _textOrNull(json['stage']),
      width: _intOrNull(json['width']),
      height: _intOrNull(json['height']),
      megapixels: _doubleOrNull(json['megapixels']),
      fileSizeBytes: _intOrNull(json['file_size_bytes']),
      generatedTitle: _textOrNull(json['generated_title']),
      generatedDescription: _textOrNull(json['generated_description']),
      generatedKeywords: _stringListOrNull(json['generated_keywords']),
      downloadName: _textOrNull(json['download_name']),
      suggestedFilename: _textOrNull(json['suggested_filename']),
      uploadFilename: _textOrNull(json['upload_filename']),
      // Backend field is `is_used` (schemas.py RecordResponse).
      used: _boolOrNull(json['is_used']),
      usedAt: _dateTimeOrNull(json['used_at']),
      acceptanceScore: _doubleOrNull(json['acceptance_score']),
      category: _intOrNull(json['category']),
      groupId: _textOrNull(json['group_id']),
      batchId: _textOrNull(json['batch_id']),
      promptId: _textOrNull(json['prompt_id']),
      createdAt: _dateTimeOrNull(json['created_at']),
      updatedAt: _dateTimeOrNull(json['updated_at']),
      stageUpdatedAt: _dateTimeOrNull(json['stage_updated_at']),
    );
  }

  String _text(Object? value) => value?.toString() ?? '';

  /// `state` when the backend ships it; otherwise a best-effort mapping of
  /// the legacy `status`/`stage` pair so old cached payloads still land on
  /// a sensible lifecycle position instead of crashing the screens.
  String _state() {
    final Object? raw = json['state'];
    if (raw is String && raw.isNotEmpty) {
      return raw;
    }
    final String stage = _text(json['stage']);
    final String status = _text(json['status']);
    if (stage == 'PUBLISHED' || status == 'PUBLISHED') {
      return 'PUBLISHED';
    }
    if (status == 'READY') {
      return 'READY_TO_PUBLISH';
    }
    if (status == 'FLAGGED' ||
        stage == 'OCR_REJECTED' ||
        stage == 'INCOMPATIBLE' ||
        stage == 'QUARANTINED') {
      return 'REJECTED';
    }
    // Best-effort additions to the legacy chain: a passed/approved QC row
    // is exactly what `APPROVED` means in the state contract.
    if (status == 'APPROVED' || status == 'PASSED') {
      return 'APPROVED';
    }
    if (stage == 'METADATA_READY') {
      return 'APPROVED';
    }
    return 'COLLECTED';
  }

  /// `flags` reordered into the contract's display order ([kImageFlags]);
  /// unknown flags trail in payload order, missing → `[]`.
  List<String> _flags() {
    final List<String> raw =
        _stringListOrNull(json['flags']) ?? const <String>[];
    if (raw.isEmpty) {
      return const <String>[];
    }
    return <String>[
      for (final String flag in kImageFlags)
        if (raw.contains(flag)) flag,
      for (final String flag in raw)
        if (!kImageFlags.contains(flag)) flag,
    ];
  }

  String? _textOrNull(Object? value) =>
      value is String && value.isNotEmpty ? value : null;

  int? _intOrNull(Object? value) => value is num ? value.toInt() : null;

  double? _doubleOrNull(Object? value) => value is num ? value.toDouble() : null;

  bool? _boolOrNull(Object? value) => value is bool ? value : null;

  DateTime? _dateTimeOrNull(Object? value) =>
      value is String ? DateTime.tryParse(value) : null;

  List<String>? _stringListOrNull(Object? value) {
    if (value is! List<Object?>) {
      return null;
    }
    final List<String> items = <String>[];
    for (final Object? element in value) {
      if (element is String && element.isNotEmpty) {
        items.add(element);
      }
    }
    return items;
  }
}
