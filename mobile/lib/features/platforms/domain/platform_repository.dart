import 'platform.dart';

/// Catalogue access for the hub and coming-soon screens (03 §4 contract:
/// implementations live in `data/` and throw only [AppException]s).
abstract class PlatformRepository {
  /// Full catalogue in display order — `GET /api/platforms/` (trailing
  /// slash is mandatory, 02 §2).
  Future<List<PlatformEntry>> fetchPlatforms();

  /// One platform — `GET /api/platforms/{platform_id}`; 404 surfaces as
  /// `NotFoundException` for unknown ids (05 §2.10).
  Future<PlatformEntry> fetchPlatform(String platformId);
}
