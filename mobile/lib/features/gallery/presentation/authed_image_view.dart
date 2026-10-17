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
import 'image_state_presentation.dart';
import 'zoom_math.dart';

/// Immersive full-resolution image page for the detail pager (05 §2.6).
///
/// * Full res via `GET /api/records/{id}/file` with the session cookie —
///   never [Image.network] (no cookie → 401).
/// * Pinch zoom 1.0–4.0 driven by the app's own focal-point math
///   ([zoomAboutFocalPoint] + [panBy]/[clampCoverage] every scale frame) —
///   native [InteractiveViewer] drifted ~25 px off the fingers in the
///   widget-test repro (R8 boundary/translate corrections), so the pinch is
///   deterministic here: content stays exactly under the fingers, pan while
///   zoomed can never expose a blank edge, and the matrix is applied with
///   `alignment: null` so the on-screen pixels equal the matrix 1:1.
///   Double-tap toggles FIT ↔ 2.0× about the tap point (never origin-
///   anchored) and flips the chrome overlay; a single tap only flips the
///   chrome; single-finger drags do nothing at fit.
/// * Zoom crossings bubble through [onZoomChanged] so the pager can switch
///   to [NeverScrollableScrollPhysics] and the swipe never fights the
///   pinch (documented simplification over gesture-arena arbitration).
class AuthedImageView extends ConsumerStatefulWidget {
  const AuthedImageView({super.key, required this.record, this.onZoomChanged});

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

  /// Viewport size captured by [LayoutBuilder]; drives the focal-point math.
  Size _viewport = Size.zero;

  /// Position of the most recent double-tap down (the zoom focal point).
  Offset _doubleTapFocal = Offset.zero;

  /// Scale at the start of the current pinch gesture —
  /// [ScaleUpdateDetails.scale] is relative to gesture start, not per frame.
  double _pinchStartScale = 1.0;

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
    // Only `completed` settles a zoom tween. `forward(from: 0)` on a
    // controller left `completed` by the previous toggle first emits a
    // TRANSIENT `dismissed` at value 0 — acting on it would drop
    // `_pendingZoom` before any frame applied it, so the second
    // double-tap's zoom-out silently never ran (R5 regression).
    if (status != AnimationStatus.completed) {
      return;
    }
    _pendingZoom = null;
    _reportZoom();
  }

  void _reportZoom() {
    final bool nowZoomed = isZoomed(_transform.value);
    if (nowZoomed == _zoomed) {
      return;
    }
    _zoomed = nowZoomed;
    widget.onZoomChanged?.call(nowZoomed);
  }

  void _toggleChrome() {
    setState(() => _chromeVisible = !_chromeVisible);
  }

  /// FIT ↔ 2.0× toggle (R5): zoom-in anchors about the tap point through
  /// [zoomAboutFocalPoint] (never origin-anchored); zoom-out returns to
  /// plain identity (FIT). Chrome flips only on this deliberate gesture —
  /// pinch never hides it invisibly.
  void _handleDoubleTap() {
    if (_viewport == Size.zero) {
      return;
    }
    final Matrix4 target = isZoomed(_transform.value)
        ? doubleTapZoomOut()
        : doubleTapZoomIn(
            focalPoint: _doubleTapFocal,
            viewport: _viewport,
            previousMatrix: _transform.value,
          );
    _pendingZoom = Matrix4Tween(begin: _transform.value, end: target);
    _zoomAnim.forward(from: 0);
    setState(() => _chromeVisible = !_chromeVisible);
  }

  /// Pinch start: snapshot the scale ([ScaleUpdateDetails.scale] is
  /// cumulative from gesture start) and cancel any double-tap tween so the
  /// two paths can't overwrite each other's frames.
  void _onScaleStart(ScaleStartDetails details) {
    if (_zoomAnim.isAnimating) {
      _zoomAnim.stop();
      _pendingZoom = null;
    }
    _pinchStartScale = _transform.value.getMaxScaleOnAxis();
  }

  /// One code path for pinch AND pan: move by the focal delta (only while
  /// zoomed — a finger-drag at FIT must not shift the framing), scale about
  /// the live focal point through [zoomAboutFocalPoint], then guarantee
  /// coverage with [clampCoverage]. No inertia on release — the pager owns
  /// flicks and the clamp owns the edges.
  void _onScaleUpdate(ScaleUpdateDetails details) {
    if (_viewport == Size.zero) {
      return;
    }
    Matrix4 matrix = _transform.value;
    final Offset delta = details.focalPointDelta;
    if (delta != Offset.zero && isZoomed(matrix)) {
      matrix = panBy(previousMatrix: matrix, delta: delta, viewport: _viewport);
    }
    final double target = (_pinchStartScale * details.scale).clamp(1.0, 4.0);
    matrix = zoomAboutFocalPoint(
      targetScale: target,
      focalPoint: details.localFocalPoint,
      viewport: _viewport,
      previousMatrix: matrix,
    );
    _transform.value = clampCoverage(matrix: matrix, viewport: _viewport);
    _reportZoom();
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
        LayoutBuilder(
          builder: (BuildContext context, BoxConstraints constraints) {
            _viewport = Size(constraints.maxWidth, constraints.maxHeight);
            return GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: _toggleChrome,
              onDoubleTapDown: (TapDownDetails details) =>
                  _doubleTapFocal = details.localPosition,
              onDoubleTap: _handleDoubleTap,
              onScaleStart: _onScaleStart,
              onScaleUpdate: _onScaleUpdate,
              child: ClipRect(
                child: AnimatedBuilder(
                  animation: _transform,
                  builder: (BuildContext context, Widget? child) => Transform(
                    key: const ValueKey<String>('authed-image-matrix'),
                    transform: _transform.value,
                    // Raw matrix on screen: zoom_math's exact contract —
                    // Transform's default center alignment would conjugate
                    // the matrix and shift the anchor under the fingers.
                    alignment: null,
                    child: child,
                  ),
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
                      errorWidget:
                          (BuildContext context, String url, Object error) =>
                              Center(
                                child: ErrorView(
                                  message:
                                      'Couldn\u2019t load the full-size image.',
                                  onRetry: () => setState(
                                    () => _attempt += 1,
                                  ), // Re-keys ImageProvider.
                                ),
                              ),
                    ),
                  ),
                ),
              ),
            );
          },
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
        const Center(child: SizedBox(width: 160, child: ProgressBar())),
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
              label: stateLabel(record.state),
              tone: stateTone(record.state),
              rotation: -2,
            ),
            const SizedBox(width: AppSpacing.sm),
          ],
        ),
      ),
    );
  }
}
