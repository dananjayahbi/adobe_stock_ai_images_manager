import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/dio_factory.dart';
import '../../platforms/presentation/platforms_controller.dart';
import '../data/gallery_repository_impl.dart';
import 'gallery_group.dart';
import 'gallery_page.dart';
import 'gallery_query.dart';
import 'image_record.dart';

/// Repository wired to the shared Dio client (cookie jar + profile base URL
/// handled by `core/network`). Widget tests override this provider to fake
/// the backend without touching Dio — the gallery's single override seam.
///
/// The active platform id is captured when the provider builds, so every
/// record/group path runs through `platformPath(activePlatformId, …)`
/// (03 §3.5) and a platform switch rebuilds the repository; the controller
/// watches `activePlatformIdProvider` too and re-fetches with it.
final galleryRepositoryProvider = Provider<GalleryRepository>((ref) {
  final String platformId = ref.watch(activePlatformIdProvider);
  return GalleryRepositoryImpl(ref.watch(dioProvider), platformId);
});

/// Gallery endpoints (02 §3): a paging [GalleryQuery] lens in, entities out.
///
/// Mutations are single-record — the multi-select toolbar loops them (web
/// would ship `PATCH /records/used` + `POST /bulk-delete` in one call; the
/// frozen contract keeps the interface at single-record granularity).
abstract class GalleryRepository {
  /// `GET records?…` → `{items, total, page, page_size}` as a [GalleryPage].
  Future<GalleryPage> fetchPage(GalleryQuery query);

  /// `GET records/{id}` → one [ImageRecord].
  Future<ImageRecord> fetchById(String recordId);

  /// `GET groups` → the folder strip's cards.
  Future<List<GalleryGroup>> fetchGroups();

  /// `POST records/{id}/approve`, with optional metadata overrides.
  Future<void> approve(
    String recordId, {
    String? overrideTitle,
    String? overrideDescription,
    List<String>? overrideKeywords,
  });

  /// `PATCH records/{id}/used` — `UsedRequest {is_used}` (web's bulk call
  /// shares the same body minus `record_ids`).
  Future<void> markUsed(String recordId, {required bool used});

  /// `PATCH records/{id}/state` — `StateRequest {state}`; 200 with the full
  /// record, 400 when the transition is not allowed.
  Future<void> changeState(String recordId, String state);

  /// `POST records/{id}/reset-stage` — stage 1 again (409 once published).
  Future<void> resetStage(String recordId);

  /// `DELETE records/{id}` — row plus on-disk artifacts.
  Future<void> deleteRecord(String recordId);
}
