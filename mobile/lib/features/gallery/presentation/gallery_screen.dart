import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:lucide_flutter/lucide_flutter.dart';

import '../../../app/lifecycle_observer.dart';
import '../../../app/theme/tokens.dart';
import '../../../core/utils/app_exception.dart';
import '../../../core/widgets/connection_profile_banner.dart';
import '../../../core/widgets/error_view.dart';
import '../../../core/widgets/toast_exception.dart';
import '../domain/gallery_group.dart';
import '../domain/gallery_page.dart';
import '../domain/gallery_query.dart';
import '../domain/image_record.dart';
import 'filter_bar.dart';
import 'gallery_controller.dart';
import 'gallery_grid.dart';
import 'selection_toolbar.dart';

/// Gallery screen (05 §2.5): lens chips + folder strip over a responsive,
/// infinitely-scrolling 1:1 grid with multi-select actions.
///
/// State handling per spec — 12-tile skeleton while the first page loads,
/// three-tile footer while paging, pull-to-refresh, inline ErrorView above
/// a **stale** grid on refresh/paging failure, full ErrorView when nothing
/// was ever loaded, "Nothing matches this lens" per filter vs the
/// empty-gallery CTA state.
class GalleryScreen extends ConsumerStatefulWidget {
  const GalleryScreen({super.key});

  @override
  ConsumerState<GalleryScreen> createState() => _GalleryScreenState();
}

class _GalleryScreenState extends ConsumerState<GalleryScreen> {
  final ScrollController _scroll = ScrollController();
  final Set<String> _selected = <String>{};

  bool _selectMode = false;
  bool _showFilters = true;
  bool _loadingMore = false;
  bool _busy = false;
  Object? _inlineError;

  GalleryController get _controller =>
      ref.read(galleryControllerProvider.notifier);

  @override
  void initState() {
    super.initState();
    _scroll.addListener(_onScroll);
  }

  @override
  void dispose() {
    _scroll.removeListener(_onScroll);
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final AsyncValue<GalleryPage> pageAsync =
        ref.watch(galleryControllerProvider);
    final GalleryQuery query = _controller.query;
    final List<GalleryGroup>? groups =
        ref.watch(galleryGroupsProvider).value;
    // Resume revalidation (03 §4): refresh the gallery on foreground.
    final ProviderContainer container = ProviderScope.containerOf(context);
    AppLifecycleHooks.registerFeatureInvalidator(
      'gallery',
      () => container.invalidate(galleryControllerProvider),
    );
    // The screen knows the link is down once the outstanding failure was a
    // network one (05 §3) — the selection toolbar dims its actions then.
    final bool offline =
        (pageAsync.hasError ? pageAsync.error : _inlineError)
            is NetworkException;

    return PopScope(
      canPop: query.groupId == null,
      onPopInvokedWithResult: (bool didPop, Object? result) {
        if (!didPop) {
          _apply(query.copyWith(clearGroup: true));
        }
      },
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Gallery'),
          actions: <Widget>[
            IconButton(
              tooltip: 'Select images',
              onPressed: _toggleSelectMode,
              icon: Icon(
                _selectMode ? LucideIcons.x : LucideIcons.listChecks,
                size: 20,
              ),
            ),
            IconButton(
              tooltip: 'Filters',
              onPressed: () => setState(() => _showFilters = !_showFilters),
              icon: Icon(
                LucideIcons.listFilter,
                size: 20,
                color: _showFilters
                    ? Theme.of(context).colorScheme.primary
                    : null,
              ),
            ),
          ],
        ),
        bottomNavigationBar: _selectMode && _selected.isNotEmpty
            ? SelectionToolbar(
                count: _selected.length,
                busy: _busy,
                offline: offline,
                onCancel: () => setState(_exitSelection),
                onDownloadZip: () => unawaited(_downloadZip()),
                onDelete: () => unawaited(_confirmDelete()),
                onMarkUsed: () => unawaited(_markUsed()),
              )
            : null,
        body: Column(
          children: <Widget>[
            const ConnectionProfileBanner(),
            const SizedBox(height: AppSpacing.md),
            if (_showFilters) ...<Widget>[
              GalleryFilterBar(query: query, onChanged: _apply),
              const SizedBox(height: AppSpacing.sm),
            ],
            GroupStrip(
              groups: groups ?? const <GalleryGroup>[],
              query: query,
              onSelect: (String id) => _apply(query.copyWith(groupId: id)),
              onClear: () => _apply(query.copyWith(clearGroup: true)),
            ),
            const SizedBox(height: AppSpacing.sm),
            Expanded(child: _content(pageAsync, query, groups)),
          ],
        ),
      ),
    );
  }

  // ---------------------------------------------------------------- content

  Widget _content(
    AsyncValue<GalleryPage> pageAsync,
    GalleryQuery query,
    List<GalleryGroup>? groups,
  ) {
    final GalleryPage? page = pageAsync.value;

    // A lens switch (or platform switch) is a fresh fetch: show the
    // skeleton even though riverpod keeps the previous page attached —
    // stale rows from the *old* lens must not flash under a new query.
    if (pageAsync.isLoading) {
      return CustomScrollView(
        slivers: <Widget>[
          gallerySkeletonSliver(metrics: galleryGridMetrics(context)),
        ],
      );
    }
    if (page == null) {
      return ErrorView(
        message: pageAsync.error == null ? null : errorText(pageAsync.error!),
        onRetry: _retryAll,
      );
    }

    final Object? inline = pageAsync.hasError ? pageAsync.error : _inlineError;

    if (page.items.isEmpty) {
      final bool emptyAll =
          query.isDefaultLens && (groups == null || groups.isEmpty);
      return RefreshIndicator(
        onRefresh: _refresh,
        child: SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          child: ConstrainedBox(
            constraints: BoxConstraints(
              minHeight: MediaQuery.sizeOf(context).height * 0.5,
            ),
            child: Column(
              children: <Widget>[
                if (inline != null)
                  galleryInlineError(error: inline, onRetry: _refresh),
                galleryEmptyState(
                  lensFiltered: !emptyAll,
                  onNewBatch: () => showAppToast(
                    context,
                    'Batch wizard arrives with M4',
                    tone: ToastTone.neutral,
                  ),
                ),
              ],
            ),
          ),
        ),
      );
    }

    final ({int columns, double cellWidth}) metrics =
        galleryGridMetrics(context);
    return RefreshIndicator(
      onRefresh: _refresh,
      child: CustomScrollView(
        controller: _scroll,
        physics: const AlwaysScrollableScrollPhysics(),
        slivers: <Widget>[
          if (inline != null)
            // Sliver wrapper: galleryInlineError is a Padding (box widget).
            SliverToBoxAdapter(
              child: galleryInlineError(error: inline, onRetry: _refresh),
            ),
          galleryRecordsSliver(
            metrics: metrics,
            items: page.items,
            selectedIds: _selected,
            selectMode: _selectMode,
            onTap: _onTapRecord,
            onLongPress: _onLongPressRecord,
          ),
          if (_loadingMore) galleryFooterSliver(),
        ],
      ),
    );
  }

  // ------------------------------------------------------------------ lens

  void _apply(GalleryQuery next) => unawaited(_controller.applyQuery(next));

  Future<void> _refresh() async {
    try {
      await _controller.refresh();
      if (mounted) {
        setState(() => _inlineError = null);
      }
    } catch (error) {
      if (mounted) {
        setState(() => _inlineError = error);
      }
    }
  }

  void _retryAll() => ref.invalidate(galleryControllerProvider);

  void _onScroll() {
    if (!_scroll.hasClients) {
      return;
    }
    if (_scroll.position.pixels < _scroll.position.maxScrollExtent - 300) {
      return;
    }
    unawaited(_loadMore());
  }

  Future<void> _loadMore() async {
    if (_loadingMore || _busy) {
      return;
    }
    final GalleryPage? page = ref.read(galleryControllerProvider).value;
    if (page == null || page.items.length >= page.total) {
      return;
    }
    setState(() => _loadingMore = true);
    try {
      await _controller.loadMore();
      if (mounted && _inlineError != null) {
        setState(() => _inlineError = null);
      }
    } catch (error) {
      if (mounted) {
        setState(() => _inlineError = error);
      }
    } finally {
      if (mounted) {
        setState(() => _loadingMore = false);
      }
    }
  }

  // ------------------------------------------------------------- selection

  void _toggleSelectMode() {
    setState(() {
      if (_selectMode) {
        _exitSelection();
      } else {
        _selectMode = true;
      }
    });
  }

  void _exitSelection() {
    _selectMode = false;
    _selected.clear();
    _inlineError = null;
  }

  void _onTapRecord(ImageRecord record) {
    if (!_selectMode) {
      context.push('/gallery/${record.id}');
      return;
    }
    setState(() {
      if (!_selected.remove(record.id)) {
        _selected.add(record.id);
      }
    });
  }

  void _onLongPressRecord(ImageRecord record) {
    setState(() {
      _selectMode = true;
      _selected.add(record.id);
    });
  }

  Future<void> _downloadZip() async {
    final List<String> ids = _selected.toList(growable: false);
    setState(() => _busy = true);
    try {
      final String path = await _controller.downloadZip(ids);
      if (mounted) {
        showAppToast(context, 'ZIP saved to $path', tone: ToastTone.success);
      }
    } catch (error) {
      if (mounted) {
        showAppToast(context, errorText(error), tone: ToastTone.error);
      }
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }

  Future<void> _confirmDelete() async {
    final int count = _selected.length;
    final bool? confirmed = await confirmDeleteDialog(context, count);
    if (confirmed != true || !mounted) {
      return;
    }

    final List<String> ids = _selected.toList(growable: false);
    setState(() => _busy = true);
    try {
      await _controller.deleteRecords(ids);
      if (!mounted) {
        return;
      }
      setState(() {
        _selected.clear();
        _selectMode = false;
      });
      showAppToast(
        context,
        'Deleted $count ${count == 1 ? 'image' : 'images'}',
        tone: ToastTone.success,
      );
    } catch (error) {
      if (mounted) {
        showAppToast(context, errorText(error), tone: ToastTone.error);
      }
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }

  Future<void> _markUsed() async {
    final List<String> ids = _selected.toList(growable: false);
    setState(() => _busy = true);
    try {
      await _controller.markRecordsUsed(ids, used: true);
      if (mounted) {
        showAppToast(
          context,
          'Marked ${ids.length} ${ids.length == 1 ? 'image' : 'images'} used',
          tone: ToastTone.success,
        );
      }
    } catch (error) {
      if (mounted) {
        showAppToast(context, errorText(error), tone: ToastTone.error);
      }
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }
}
