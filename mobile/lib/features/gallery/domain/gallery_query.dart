/// Immutable gallery filter + pagination lens (05 §2.5 FilterBar).
///
/// Defaults mirror the web gallery's spirit against the `state` contract
/// (verified against `backend/routers/records.py`):
///
/// * `state` — backend accepts a **comma-separated CSV** of image states
///   (`state.split(",")`, same shape as the old `stage=` filter). The
///   default lens is `'READY_TO_PUBLISH,PUBLISHED,AS_ACCEPTED'` (queued,
///   published and Adobe-accepted records); `''` omits the param
///   (= Any state).
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
    this.state = 'READY_TO_PUBLISH,PUBLISHED,AS_ACCEPTED',
    this.used = 'all',
    this.groupId,
    this.offset = 0,
    this.limit = 60,
    this.stageUpdated = true,
  });

  /// Default lens: queued, published and Adobe-accepted records.
  static const String defaultState = 'READY_TO_PUBLISH,PUBLISHED,AS_ACCEPTED';

  final String? search;
  final String state;
  final String used;
  final String? groupId;
  final int offset;
  final int limit;
  final bool stageUpdated;

  /// True when nothing narrows the default lens (drives the empty-all vs
  /// "Nothing matches this lens" split in 05 §2.5).
  bool get isDefaultLens =>
      (search == null || search!.isEmpty) &&
      state == defaultState &&
      used == 'all' &&
      groupId == null;

  GalleryQuery copyWith({
    String? search,
    String? state,
    String? used,
    String? groupId,
    int? offset,
    int? limit,
    bool? stageUpdated,
    bool clearGroup = false,
  }) {
    return GalleryQuery(
      search: search ?? this.search,
      state: state ?? this.state,
      used: used ?? this.used,
      groupId: clearGroup ? null : (groupId ?? this.groupId),
      offset: offset ?? this.offset,
      limit: limit ?? this.limit,
      stageUpdated: stageUpdated ?? this.stageUpdated,
    );
  }

  /// Wire params in `frontend-new` order: limit, offset, search, state,
  /// used, group_id, stage_updated — omitting empty/default values exactly
  /// like `lib/records.ts#fetchRecords`. No `sort` param exists (gap 12).
  Map<String, String> toQuery() {
    return <String, String>{
      'limit': '$limit',
      'offset': '$offset',
      if (search != null && search!.trim().isNotEmpty)
        'search': search!.trim(),
      if (state.isNotEmpty) 'state': state,
      if (used != 'all') 'used': used,
      'group_id': groupId == null || groupId!.isEmpty ? 'none' : groupId!,
      if (stageUpdated) 'stage_updated': 'true',
    };
  }

  @override
  bool operator ==(Object other) =>
      other is GalleryQuery &&
      other.search == search &&
      other.state == state &&
      other.used == used &&
      other.groupId == groupId &&
      other.offset == offset &&
      other.limit == limit &&
      other.stageUpdated == stageUpdated;

  @override
  int get hashCode => Object.hash(
        search,
        state,
        used,
        groupId,
        offset,
        limit,
        stageUpdated,
      );
}
