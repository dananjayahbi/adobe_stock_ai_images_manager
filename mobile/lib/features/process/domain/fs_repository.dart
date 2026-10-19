import 'package:ai_stock_studio/features/process/data/fs_repository_impl.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/dio_factory.dart';
import '../../platforms/presentation/platforms_controller.dart';

/// Source-folder browser backed by the shared Dio client (cookie jar +
/// profile base URL handled by `core/network`). A **separate** seam from
/// `processRepositoryProvider` (same override style): the base repository
/// interface stays untouched so out-of-domain fakes keep compiling.
final fsRepositoryProvider = Provider<FsRepository>((ref) {
  final String platformId = ref.watch(activePlatformIdProvider);
  return FsRepositoryImpl(ref.watch(dioProvider), platformId);
});

/// Contract for `GET fs/*` — implemented by `FsRepositoryImpl`.
abstract class FsRepository {
  /// `GET fs/root` → whether a source folder is configured (+ its path).
  Future<FsRoot> fetchRoot();

  /// `GET fs/list?path=rel` → one directory's listings (`path` may be `''`
  /// for the configured root).
  Future<FsListing> fetchListing(String path);

  /// `GET fs/thumb?path=rel` URL fragment for [path] (relative), to be
  /// prefixed with the connection profile's base URL by the caller.
  String thumbUrl(String path);
}

/// `GET fs/root` → `{configured, path|null, exists}`.
class FsRoot {
  const FsRoot({
    required this.configured,
    required this.path,
    required this.exists,
  });

  factory FsRoot.fromJson(Map<String, Object?> json) => FsRoot(
    configured: json['configured'] == true,
    path: json['path'] is String && (json['path']! as String).isNotEmpty
        ? json['path']! as String
        : null,
    exists: json['exists'] == true,
  );

  /// False → the picker renders the "Source folder not configured" state.
  final bool configured;

  /// Absolute folder path on the studio machine (informational).
  final String? path;

  /// Whether [path] still exists on disk.
  final bool exists;
}

/// One directory entry of `GET fs/list`.
class FsListing {
  const FsListing({
    required this.path,
    required this.segments,
    required this.parent,
    required this.dirs,
    required this.files,
  });

  /// Defensive parse (M2 contract): a wrong container is the repository's
  /// job to reject; unknown rows are skipped.
  ///
  /// [fallbackPath] is the requested `path` value, used when the payload
  /// omits an echo of it.
  factory FsListing.fromJson(
    Map<String, Object?> json, {
    String fallbackPath = '',
  }) {
    final Object? rawPath = json['path'];
    final String path = rawPath is String
        ? rawPath
        : (rawPath == null ? fallbackPath : rawPath.toString());

    final List<String> segments = <String>[];
    final Object? rawSegments = json['segments'];
    if (rawSegments is List<Object?>) {
      for (final Object? segment in rawSegments) {
        if (segment != null) {
          segments.add(segment.toString());
        }
      }
    }
    // Defensive breadcrumb: derive from the path when the server omits it.
    final List<String> resolvedSegments = segments.isNotEmpty || path.isEmpty
        ? segments
        : path.split('/').where((String s) => s.isNotEmpty).toList();

    final Object? rawParent = json['parent'];
    final String? parent = rawParent is String && rawParent.isNotEmpty
        ? rawParent
        : null;

    final List<String> dirs = <String>[];
    final Object? rawDirs = json['dirs'];
    if (rawDirs is List<Object?>) {
      for (final Object? row in rawDirs) {
        final Object? name = row is Map<Object?, Object?> ? row['name'] : null;
        if (name != null && name.toString().isNotEmpty) {
          dirs.add(name.toString());
        }
      }
    }

    final List<FsFile> files = <FsFile>[];
    final Object? rawFiles = json['files'];
    if (rawFiles is List<Object?>) {
      for (final Object? row in rawFiles) {
        if (row is Map<Object?, Object?>) {
          final Object? name = row['name'];
          if (name == null || name.toString().isEmpty) {
            continue;
          }
          files.add(
            FsFile(
              name: name.toString(),
              size: row['size'] is num ? (row['size']! as num).toInt() : null,
              mtime: row['mtime'] is String
                  ? DateTime.tryParse(row['mtime']! as String)
                  : null,
            ),
          );
        }
      }
    }

    return FsListing(
      path: path,
      segments: resolvedSegments,
      parent: parent,
      dirs: dirs,
      files: files,
    );
  }

  /// Rel path of this directory (`''` at the configured root).
  final String path;

  /// Path components from the root — breadcrumbs (first chip is the
  /// screen's own "Source" label, so it excludes the root itself).
  final List<String> segments;

  /// Rel path of the parent directory; null at the root.
  final String? parent;

  /// Sub-directory names (server-sorted).
  final List<String> dirs;

  /// Image files (jpg/jpeg/png, server-sorted).
  final List<FsFile> files;
}

/// One image file row of `GET fs/list.files`.
class FsFile {
  const FsFile({required this.name, this.size, this.mtime});

  /// File name (compose rel paths with [FsListing.path]).
  final String name;

  /// Bytes, when the payload carries it.
  final int? size;

  /// Modified time, when the payload carries an ISO value.
  final DateTime? mtime;
}
