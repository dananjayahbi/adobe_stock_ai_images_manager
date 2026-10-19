import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_flutter/lucide_flutter.dart';

import 'package:ai_stock_studio/app/theme/tokens.dart';
import 'package:ai_stock_studio/core/network/session_cookie.dart';
import 'package:ai_stock_studio/core/storage/image_cache.dart';
import 'package:ai_stock_studio/features/settings/data/profile_store.dart';
import 'skeleton_loader.dart';

/// Returns the file name portion of a record path, tolerant of both `/` and
/// `\` separators — DB rows store absolute paths (07 §"Thumbnail URLs").
String thumbnailBasename(String path) {
  final String normalized = path.replaceAll(r'\', '/');
  final int index = normalized.lastIndexOf('/');
  if (index < 0) {
    return normalized;
  }
  return normalized.substring(index + 1);
}

/// Grid/detail thumbnail served by `{baseUrl}/thumbnails/{basename}`.
///
/// Sends the per-profile session cookie when one is known, decodes at a
/// capped width for grid efficiency, shimmers while loading and falls back
/// to an icon on failure (04 §5).
class Thumbnail extends ConsumerWidget {
  const Thumbnail({
    super.key,
    required this.path,
    this.size,
    this.radius,
  });

  /// Absolute record path on the studio machine; only the basename is used.
  final String path;

  /// Optional square edge length; without it the thumbnail fills the
  /// incoming constraints.
  final double? size;

  /// Corner radius; defaults to [AppRadii.sm].
  final BorderRadius? radius;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final profile = ref.watch(activeProfileProvider);
    final String? cookie = ref.watch(sessionCookieHeaderProvider);
    final BorderRadius effectiveRadius =
        radius ?? const BorderRadius.all(Radius.circular(AppRadii.sm));
    final String base = profile.baseUrl.replaceAll(RegExp(r'/+$'), '');
    final String imageUrl =
        '$base/thumbnails/${thumbnailBasename(path)}';

    final Widget image = CachedNetworkImage(
      imageUrl: imageUrl,
      cacheManager: imageCacheManager,
      httpHeaders: cookie == null
          ? null
          : <String, String>{'Cookie': cookie},
      fit: BoxFit.cover,
      memCacheWidth: 400,
      placeholder: (BuildContext context, String url) =>
          const SkeletonLoader(),
      errorWidget: (BuildContext context, String url, Object error) {
        return ColoredBox(
          color: AppColors.parchment200,
          child: Center(
            child: Icon(
              LucideIcons.imageOff,
              size: 24,
              color: AppColors.ink400,
            ),
          ),
        );
      },
    );

    final Widget clipped = ClipRRect(
      borderRadius: effectiveRadius,
      child: image,
    );
    if (size != null) {
      return SizedBox(width: size, height: size, child: clipped);
    }
    return clipped;
  }
}
