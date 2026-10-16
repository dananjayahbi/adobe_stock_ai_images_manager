import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/utils/app_exception.dart';
import '../../../core/widgets/progress_bar.dart';
import '../../../core/widgets/stamp_badge.dart';
import '../../../core/widgets/stamp_in.dart';
import '../../../core/widgets/error_view.dart';
import '../domain/gallery_page.dart';
import '../domain/gallery_repository.dart';
import '../domain/image_record.dart';
import 'authed_image_view.dart';
import 'gallery_controller.dart';
import 'image_state_presentation.dart';
import 'metadata_sheet.dart';
import 'review_action_bar.dart';

/// States that earn the persistent over-image stamp — everything past the
/// pipeline's approval gate (queued, shipped or accepted by Adobe).
const Set<String> _preStampedStates = <String>{
  'APPROVED',
  'READY_TO_PUBLISH',
  'PUBLISHED',
  'AS_ACCEPTED',
};

/// Image Detail / Review — the operator's core review loop (05 §2.6).
///
/// Pushed OUTSIDE the shell at `/gallery/:recordId`, so tabs are hidden and
/// the screen is fully immersive.
class GalleryDetailScreen extends ConsumerWidget {
  const GalleryDetailScreen({super.key, required this.recordId});

  /// Route parameter: record opened from the grid/dashboard deep link.
  final String recordId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return _DetailBody(recordId: recordId);
  }
}

/// Mutable pager/chrome/stamp state lives here — [GalleryDetailScreen] is a
/// [ConsumerWidget] by route contract, so state needs a child StatefulWidget.
class _DetailBody extends ConsumerStatefulWidget {
  const _DetailBody({required this.recordId});

  final String recordId;

  @override
  ConsumerState<_DetailBody> createState() => _DetailBodyState();
}

class _DetailBodyState extends ConsumerState<_DetailBody> {
  late final PageController _pageController;
  Timer? _stampTimer;

  ImageRecord? _record;
  bool _loading = true;
  Object? _error;

  /// Last known network health; NetworkException sets it, a successful
  /// fetch/action clears it. Drives the offline note + disabled actions.
  bool _offline = false;
  bool _zoomed = false;

  /// Transient ~1.2 s state overlay right after a successful approve —
  /// the approve contract flips the record to READY_TO_PUBLISH.
  bool _stampVisible = false;
  int _stampSeq = 0;

  /// Record id this pager is actually showing (page changes update it
  /// before the route catches up — see [_onPageChanged]).
  late String _currentId;

  /// Page the controller is known to sit on; a mismatch schedules a jump.
  int _syncedIndex = 0;
  bool _jumpPending = false;

  /// Whether the PageView has ever attached its controller — before the
  /// first attach a jump cannot run, so builds keep rescheduling it.
  bool _pageEverAttached = false;

  /// Page ids last seen by build — [_onPageChanged] resolves positions
  /// against it.
  List<ImageRecord> _pages = const <ImageRecord>[];

  /// Set once an approve succeeded this visit — the just-approved record
  /// never pre-stamps itself (its overlay is the transient one).
  String? _justApprovedFor;

  @override
  void initState() {
    super.initState();
    _currentId = widget.recordId;
    _pageController = PageController();
    _fetch();
  }

  @override
  void didUpdateWidget(covariant _DetailBody oldWidget) {
    super.didUpdateWidget(oldWidget);
    // context.replace() from onPageChanged echoes back with a recordId we
    // already track — only an *external* route rewrite needs a refetch.
    if (oldWidget.recordId != widget.recordId &&
        widget.recordId != _currentId) {
      _currentId = widget.recordId;
      _justApprovedFor = null;
      _syncedIndex = -1;
      _stampTimer?.cancel();
      _stampVisible = false;
      unawaited(_fetch());
    }
  }

  @override
  void dispose() {
    _stampTimer?.cancel();
    _pageController.dispose();
    super.dispose();
  }

  Future<ImageRecord?> _fetch({bool silent = false}) async {
    final String id = _currentId;
    if (!silent && mounted) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }
    try {
      final ImageRecord record =
          await ref.read(galleryRepositoryProvider).fetchById(id);
      if (!mounted || id != _currentId) {
        return null;
      }
      setState(() {
        _record = record;
        _loading = false;
        _error = null;
        _offline = false;
      });
      return record;
    } catch (error) {
      if (!mounted || id != _currentId) {
        return null;
      }
      setState(() {
        _loading = false;
        _error = error;
        if (error is NetworkException) {
          _offline = true;
        }
        if (silent && error is NotFoundException) {
          _record = null; // Deleted elsewhere → dead-end state (05 §2.6).
        }
      });
      return null;
    }
  }

  void _retry() {
    unawaited(_fetch());
  }

  void _handleRecordChanged() {
    unawaited(_syncAfterAction());
  }

  /// One network round trip per action: the silent detail refetch also
  /// patches its row into the gallery list locally, so the grid never
  /// refetches on top of it (no invalidate → no double reload).
  Future<void> _syncAfterAction() async {
    final ImageRecord? fresh = await _fetch(silent: true);
    if (fresh == null || !mounted) {
      return;
    }
    ref.read(galleryControllerProvider.notifier).patchRecord(fresh);
  }

  void _handleConnectivityChanged(bool online) {
    // Already in the target state? (target offline == !online)
    if (_offline == !online) {
      return;
    }
    if (mounted) {
      setState(() => _offline = !online);
    }
  }

  void _handleApproved() {
    _justApprovedFor = _currentId;
    _stampTimer?.cancel();
    if (mounted) {
      setState(() {
        _stampVisible = true;
        _stampSeq += 1;
      });
    }
    _stampTimer = Timer(const Duration(milliseconds: 1200), () {
      if (mounted) {
        setState(() => _stampVisible = false);
      }
    });
    // Single refetch: the detail GET doubles as the list patch — no whole-
    // list invalidate, no second network round trip (05 speed budget).
    unawaited(_syncAfterAction());
  }

  void _onZoomChanged(bool zoomed) {
    if (_zoomed != zoomed && mounted) {
      setState(() => _zoomed = zoomed);
    }
  }

  void _onPageChanged(int next) {
    if (next < 0 || next >= _pages.length) {
      return;
    }
    final ImageRecord record = _pages[next];
    if (record.id == _currentId) {
      return;
    }
    // Swap state FIRST, then rewrite the route with context.replace —
    // go() would pop the shell context; replace keeps the pushed entry so
    // back always returns to the Gallery grid (05 §1.2 back rule).
    _currentId = record.id;
    _syncedIndex = next;
    _zoomed = false;
    _stampTimer?.cancel();
    _stampVisible = false;
    if (mounted) {
      setState(() {
        _record = record;
        _loading = false;
        _error = null;
      });
    }
    if (record.id != widget.recordId) {
      context.replace('/gallery/${record.id}');
    }
  }

  void _scheduleJump(int target) {
    if (_jumpPending) {
      return;
    }
    _jumpPending = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _jumpPending = false;
      if (!mounted || !_pageController.hasClients) {
        return; // PageView not built yet — a later build reschedules.
      }
      _pageEverAttached = true;
      final double? page = _pageController.page;
      if (page == null || page.round() != target) {
        _pageController.jumpToPage(target);
      }
    });
  }

  /// Neighbour set: the current filtered Gallery list when available,
  /// otherwise a single-page fallback (loading / error / record off-list).
  List<ImageRecord> _pagesFor(List<ImageRecord> items) {
    final ImageRecord? current = _record;
    final int at = items.indexWhere((ImageRecord r) => r.id == _currentId);
    if (at < 0) {
      return current == null
          ? const <ImageRecord>[]
          : <ImageRecord>[current];
    }
    final List<ImageRecord> pages = List<ImageRecord>.of(items);
    if (current != null && current.id == _currentId) {
      pages[at] = current; // Freshest status wins over the list copy.
    }
    return pages;
  }

  int _indexOf(List<ImageRecord> pages) {
    final int at = pages.indexWhere((ImageRecord r) => r.id == _currentId);
    return at < 0 ? 0 : at;
  }

  void _goGallery() {
    final GoRouter? router = GoRouter.maybeOf(context);
    if (router != null) {
      router.go('/gallery');
      return;
    }
    Navigator.of(context).maybePop();
  }

  @override
  Widget build(BuildContext context) {
    final AsyncValue<GalleryPage> pageAsync =
        ref.watch(galleryControllerProvider);
    final List<ImageRecord> items =
        pageAsync.value?.items ?? const <ImageRecord>[];
    final List<ImageRecord> pages = _pagesFor(items);
    _pages = pages;
    final int index = _indexOf(pages);
    if (index != _syncedIndex || !_pageEverAttached) {
      _syncedIndex = index;
      _scheduleJump(index);
    }

    final ImageRecord? record = _record;
    final bool notFound = _error is NotFoundException;
    // Persistent over-image stamp for records sitting past approval —
    // gated off for the record just approved, whose transient overlay
    // plays first (05 §2.6). The transient is approve's contract result
    // (APPROVED|REJECTED → READY_TO_PUBLISH); the persistent one wears
    // the record's own state.
    final bool transientStamp = _stampVisible;
    final bool stampUp =
        transientStamp ||
        (record != null &&
            _preStampedStates.contains(record.state) &&
            _justApprovedFor != record.id);
    final String stampState = transientStamp
        ? 'READY_TO_PUBLISH'
        : record?.state ?? 'READY_TO_PUBLISH';

    return Scaffold(
      backgroundColor: Colors.black,
      body: Stack(
        children: <Widget>[
          _media(pages, record),
          if (stampUp)
            Positioned.fill(
              child: IgnorePointer(
                child: Center(
                  child: StampIn(
                    key: ValueKey<String>('$_currentId#$_stampSeq'),
                    child: Transform.scale(
                      scale: 2.4,
                      child: StampBadge(
                        label: stateLabel(stampState),
                        tone: stateTone(stampState),
                        rotation: -3,
                      ),
                    ),
                  ),
                ),
              ),
            ),
          if (notFound && record == null)
            Positioned.fill(
              child: Center(
                child: ErrorView(
                  message: 'This image no longer exists on the studio.',
                  onRetry: _goGallery, // Tap → back to the Gallery (05 §2.6).
                ),
              ),
            )
          else if (!(record == null && notFound))
            Positioned.fill(
              child: MetadataSheet(
                record: record,
                loading: record == null && _loading,
                error: record == null ? _error : null,
                onRetry: _retry,
                footer: record == null ? null : _actionBar(record),
              ),
            ),
        ],
      ),
    );
  }

  Widget _media(List<ImageRecord> pages, ImageRecord? record) {
    if (record == null) {
      return Center(
        child: _error == null
            ? const SizedBox(width: 160, child: ProgressBar())
            : const SizedBox.shrink(),
      );
    }
    return Positioned.fill(
      child: PageView.builder(
        controller: _pageController,
        // Swipe wins only at zoom 1.0 — while zoomed the pager is inert
        // (documented simplification of gesture arbitration, 05 §2.6).
        physics: _zoomed
            ? const NeverScrollableScrollPhysics()
            : const PageScrollPhysics(),
        onPageChanged: _onPageChanged,
        itemCount: pages.length,
        itemBuilder: (BuildContext context, int i) => AuthedImageView(
          key: ValueKey<String>(pages[i].id),
          record: pages[i],
          onZoomChanged: _onZoomChanged,
        ),
      ),
    );
  }

  Widget _actionBar(ImageRecord record) {
    return ReviewActionBar(
      record: record,
      offline: _offline,
      onApproved: _handleApproved,
      onRecordChanged: _handleRecordChanged,
      onDeleted: _goGallery,
      onConnectivityChanged: _handleConnectivityChanged,
    );
  }
}
