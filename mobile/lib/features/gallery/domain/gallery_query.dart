/// Immutable gallery filter + pagination lens (05 §2.5 FilterBar).
///
/// Defaults mirror `frontend-new`'s gallery page exactly (verified against
/// `backend/routers/records.py`):
///
/// * `stage` — backend accepts a **comma-separated CSV** of `PipelineStage`
///   values (`stage.split(",")`, uppercased + enum-validated). The web
///   default lens is `'METADATA_READY,PUBLISHED'` ("Ready to publish"), so
///   that is our default. `''` omits the param (= Any stage, web parity).
/// * `used` — `all|used|unused`; the web client omits the param when
///   `'all'` (backend default), so we do too.
/// * `groupId` — the web gallery **always** sends `group_id`, defaulting to
///   the `'none'` sentinel (top level = ungrouped images + folder strip).
///   `null` here maps to `group_id=none` in [toQuery] (05 §2.5 folder scope
///   `/gallery?group=<id>` ↔ `groupId=<id>`).
/// * `limit` 60 per M3 roadmap (page size 60, sentinel-guarded).
/// * `stageUpdated` — the web gallery page always sends `stage_updated=true`
///   (images a pipeline has touched); roadmap M3 lists it as a gallery_api
///   param, so it rides along with the same default.
class GalleryQuery {
  const GalleryQuery({
    this.search,
    this.stage = 'METADATA_READY,PUBLISHED',
    this.used = 'all',
    this.groupId,
    this.offset = 0,
    this.limit = 60,
    this.stageUpdated = true,
  });

  /// Default lens: the web gallery's "Ready to publish" pair.
  static const String defaultStage = 'METADATA_READY,PUBLISHED';

  final String? search;
  final String stage;
  final String used;
  final String? groupId;
  final int offset;
  final int limit;
  final bool stageUpdated;

  /// True when nothing narrows the default lens (drives the empty-all vs
  /// "Nothing matches this lens" split in 05 §2.5).
  bool get isDefaultLens =>
      (search == null || search!.isEmpty) &&
      stage == defaultStage &&
      used == 'all' &&
      groupId == null;

  GalleryQuery copyWith({
    String? search,
    String? stage,
    String? used,
    String? groupId,
    int? offset,
    int? limit,
    bool? stageUpdated,
    bool clearGroup = false,
  }) {
    return GalleryQuery(
      search: search ?? this.search,
      stage: stage ?? this.stage,
      used: used ?? this.used,
      groupId: clearGroup ? null : (groupId ?? this.groupId),
      offset: offset ?? this.offset,
      limit: limit ?? this.limit,
      stageUpdated: stageUpdated ?? this.stageUpdated,
    );
  }

  /// Wire params in `frontend-new` order: limit, offset, search, stage,
  /// used, group_id, stage_updated — omitting empty/default values exactly
  /// like `lib/records.ts#fetchRecords`. No `sort` param exists (gap 12).
  Map<String, String> toQuery() {
    return <String, String>{
      'limit': '$limit',
      'offset': '$offset',
      if (search != null && search!.trim().isNotEmpty)
        'search': search!.trim(),
      if (stage.isNotEmpty) 'stage': stage,
      if (used != 'all') 'used': used,
      'group_id': groupId == null || groupId!.isEmpty ? 'none' : groupId!,
      if (stageUpdated) 'stage_updated': 'true',
    };
  }

  @override
  bool operator ==(Object other) =>
      other is GalleryQuery &&
      other.search == search &&
      other.stage == stage &&
      other.used == used &&
      other.groupId == groupId &&
      other.offset == offset &&
      other.limit == limit &&
      other.stageUpdated == stageUpdated;

  @override
  int get hashCode => Object.hash(
        search,
        stage,
        used,
        groupId,
        offset,
        limit,
        stageUpdated,
      );
}
