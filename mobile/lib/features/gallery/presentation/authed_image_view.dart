import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:lucide_flutter/lucide_flutter.dart';

import '../../../app/theme/tokens.dart';
import '../../../core/network/session_cookie.dart';
import '../../../core/utils/platform_paths.dart';
import '../../../core/widgets/error_view.dart';
import '../../../core/widgets/progress_bar.dart';
import '../../../core/widgets/stamp_badge.dart';
import '../../../core/widgets/thumbnail.dart';
import '../../settings/data/profile_store.dart';
import '../../platforms/presentation/platforms_controller.dart';
import '../domain/image_record.dart';
import 'metadata_sheet.dart';

/// Immersive full-resolution image page for the detail pager (05 §2.6).
///
/// * Full res via `GET /api/records/{id}/file` with the session cookie —
///   never [Image.network] (no cookie → 401).
/// * Pinch zoom 1.0–4.0 ([InteractiveViewer]); double-tap toggles 1.0 ↔ 2.0
///   and flips the chrome overlay; a single tap only flips the chrome.
/// * Zoom crossings bubble through [onZoomChanged] so the pager can switch
///   to [NeverScrollableScrollPhysics] and the swipe never fights the
///   pinch (documented simplification over gesture-arena arbitration).
class AuthedImageView extends ConsumerStatefulWidget {
  const AuthedImageView({
    super.key,
    required this.record,
    this.onZoomChanged,
  });

  /// Record to render; [ImageRecord.id] drives the file endpoint.
  final ImageRecord record;

  /// Fires when the effective zoom crosses 1.0 (false → 1.0, true → >1.0).
  final ValueChanged<bool>? onZoomChanged;

  @override
  ConsumerState<AuthedImageView> createState() => _AuthedImageViewState();
}

class _AuthedImageViewState extends ConsumerState<AuthedImageView>
    with SingleTickerProviderStateMixin {
  late final TransformationController _transform;
  late final AnimationController _zoomAnim;
  Matrix4Tween? _pendingZoom;
  bool _zoomed = false;
  bool _chromeVisible = true;
  int _attempt = 0;

  @override
  void initState() {
    super.initState();
    _transform = TransformationController();
    _zoomAnim = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 250),
    );
    _zoomAnim.addListener(_applyZoomFrame);
    _zoomAnim.addStatusListener(_onZoomStatus);
  }

  @override
  void dispose() {
    _zoomAnim.removeListener(_applyZoomFrame);
    _zoomAnim.removeStatusListener(_onZoomStatus);
    _zoomAnim.dispose();
    _transform.dispose();
    super.dispose();
  }

  void _applyZoomFrame() {
    final Matrix4Tween? tween = _pendingZoom;
    if (tween != null) {
      _transform.value = tween.evaluate(_zoomAnim.view);
    }
  }

  void _onZoomStatus(AnimationStatus status) {
    if (status == AnimationStatus.completed ||
        status == AnimationStatus.dismissed) {
      _pendingZoom = null;
      _reportZoom();
    }
  }

  void _reportZoom() {
    final bool nowZoomed = _transform.value.getMaxScaleOnAxis() > 1.01;
    if (nowZoomed == _zoomed) {
      return;
    }
    _zoomed = nowZoomed;
    widget.onZoomChanged?.call(nowZoomed);
  }

  void _toggleChrome() {
    setState(() => _chromeVisible = !_chromeVisible);
  }

  void _handleDoubleTap() {
    final double scale = _transform.value.getMaxScaleOnAxis();
    final Matrix4 target = scale > 1.01
        ? Matrix4.identity()
        : Matrix4.identity()..scaleByDouble(2.0, 2.0, 2.0, 1.0);
    _pendingZoom = Matrix4Tween(begin: _transform.value, end: target);
    _zoomAnim.forward(from: 0);
    setState(() => _chromeVisible = !_chromeVisible);
  }

  void _pop() {
    final GoRouter? router = GoRouter.maybeOf(context);
    if (router == null) {
      Navigator.of(context).maybePop();
      return;
    }
    if (router.canPop()) {
      router.pop();
    } else {
      router.go('/gallery');
    }
  }

  String get _fileUrl {
    final String base = ref
        .watch(activeProfileProvider)
        .baseUrl
        .replaceAll(RegExp(r'/+$'), '');
    final String platformId = ref.watch(activePlatformIdProvider);
    return '$base${platformPath(platformId, 'records/${widget.record.id}/file')}';
  }

  @override
  Widget build(BuildContext context) {
    final String? cookie = ref.watch(sessionCookieHeaderProvider);
    return Stack(
      fit: StackFit.expand,
      children: <Widget>[
        GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: _toggleChrome,
          onDoubleTap: _handleDoubleTap,
          child: InteractiveViewer(
            transformationController: _transform,
            minScale: 1.0,
            maxScale: 4.0,
            alignment: Alignment.center,
            onInteractionStart: (_) {},
            onInteractionUpdate: (_) => _reportZoom(),
            onInteractionEnd: (_) => _reportZoom(),
            child: Semantics(
              // The full-size image is the screen's content: label it with
              // the record's title for screen readers (04 §4).
              image: true,
              label: widget.record.filename,
              child: CachedNetworkImage(
                key: ValueKey<String>('${widget.record.id}#$_attempt'),
                imageUrl: _fileUrl,
                httpHeaders: cookie == null
                    ? null
                    : <String, String>{'Cookie': cookie},
                fit: BoxFit.contain,
                memCacheWidth: 1280,
                placeholder: (BuildContext context, String url) =>
                    _thumbnailPlaceholder(),
                errorWidget: (BuildContext context, String url, Object error) =>
                    Center(
                  child: ErrorView(
                    message: 'Couldn\u2019t load the full-size image.',
                    onRetry: () =>
                        setState(() => _attempt += 1), // Re-keys ImageProvider.
                  ),
                ),
              ),
            ),
          ),
        ),
        Positioned(
          top: 0,
          left: 0,
          right: 0,
          child: SafeArea(
            bottom: false,
            child: IgnorePointer(
              ignoring: !_chromeVisible,
              child: AnimatedOpacity(
                opacity: _chromeVisible ? 1 : 0,
                duration: const Duration(milliseconds: 220),
                child: _ChromeBar(record: widget.record, onBack: _pop),
              ),
            ),
          ),
        ),
      ],
    );
  }

  /// Fullscreen low-cost stand-in: the stored thumbnail + brass spinner.
  Widget _thumbnailPlaceholder() {
    final String? thumb = widget.record.thumbnailPath;
    return Stack(
      fit: StackFit.expand,
      children: <Widget>[
        thumb == null
            ? const ColoredBox(color: AppColors.parchment100)
            : Thumbnail(path: thumb),
        const Center(
          child: SizedBox(width: 160, child: ProgressBar()),
        ),
      ],
    );
  }
}

/// Overlay chrome (back · filename · status stamp) — lives per page so
/// double-tap can toggle it page-locally (05 §2.6 gestures).
class _ChromeBar extends StatelessWidget {
  const _ChromeBar({required this.record, required this.onBack});

  final ImageRecord record;
  final VoidCallback onBack;

  @override
  Widget build(BuildContext context) {
    final TextTheme textTheme = Theme.of(context).textTheme;
    return DecoratedBox(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: <Color>[Color(0xE6000000), Colors.transparent],
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.xs,
          vertical: AppSpacing.xs,
        ),
        child: Row(
          children: <Widget>[
            IconButton(
              onPressed: onBack,
              tooltip: 'Back',
              icon: const Icon(LucideIcons.arrowLeft, color: AppColors.ink800),
            ),
            const SizedBox(width: AppSpacing.xs),
            Expanded(
              child: Text(
                record.filename,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: textTheme.titleSmall?.copyWith(
                  color: AppColors.ink800,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            StampBadge(
              label: record.status,
              tone: statusTone(record.status),
              rotation: -2,
            ),
            const SizedBox(width: AppSpacing.sm),
          ],
        ),
      ),
    );
  }
}
