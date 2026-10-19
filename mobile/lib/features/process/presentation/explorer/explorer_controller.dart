import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/utils/app_exception.dart';
import '../../../settings/data/profile_store.dart';
import '../../domain/fs_repository.dart';

/// Picker failures must surface immediately — never sit behind riverpod's
/// default exponential auto-retry (same rule as
/// `galleryControllerProvider`; manual retry is the way back).
Duration? _noRetry(int retryCount, Object error) => null;

/// `GET fs/root` + `GET fs/list` → the `/process/pick` browser state.
///
/// Screen states: [AsyncLoading] without a value → skeleton grid;
/// [UnconfiguredSourceException] → the "Source folder not configured"
/// empty state; any other error → [ErrorView] + retry; data → breadcrumbs,
/// folder cards and the image grid.
final explorerControllerProvider =
    AsyncNotifierProvider.autoDispose<ExplorerController, ExplorerState>(
      ExplorerController.new,
      retry: _noRetry,
    );

/// The configured source folder is missing (root `configured=false`, or a
/// listing answered 400 unconfigured).
final class UnconfiguredSourceException implements Exception {
  const UnconfiguredSourceException();
}

/// One loaded directory of the source folder plus the in-flight selection.
class ExplorerState {
  const ExplorerState({
    required this.path,
    required this.segments,
    required this.parent,
    required this.dirs,
    required this.files,
    required this.selected,
    required this.loading,
    required this.thumbBase,
  });

  /// Rel path of the open directory (`''` at the configured root).
  final String path;

  /// Path components from the root → breadcrumb chips.
  final List<String> segments;

  /// Rel path of the parent directory (null at the root).
  final String? parent;

  /// Sub-directory names of [path].
  final List<String> dirs;

  /// Image files of [path] (jpg/jpeg/png).
  final List<FsFile> files;

  /// Selected images as **rel paths** (`'a.jpg'` at the root,
  /// `'sub/b.jpg'` deeper) — survives folder navigation.
  final Set<String> selected;

  /// A directory fetch is in flight (previous content stays on screen).
  final bool loading;

  /// Connection-profile base URL (no trailing slash) — thumb URLs are
  /// `thumbBase + fsRepository.thumbUrl(rel)`.
  final String thumbBase;

  /// Rel path of [name] inside this directory: root files are the bare
  /// name, children join with one `/`.
  String relPath(String name) => path.isEmpty ? name : '$path/$name';

  ExplorerState copyWith({
    String? path,
    List<String>? segments,
    String? parent,
    List<String>? dirs,
    List<FsFile>? files,
    Set<String>? selected,
    bool? loading,
    String? thumbBase,
  }) => ExplorerState(
    path: path ?? this.path,
    segments: segments ?? this.segments,
    parent: parent ?? this.parent,
    dirs: dirs ?? this.dirs,
    files: files ?? this.files,
    selected: selected ?? this.selected,
    loading: loading ?? this.loading,
    thumbBase: thumbBase ?? this.thumbBase,
  );
}

/// Browser controller: initial `fsRoot` + root listing in [build], folder
/// descent via [navigate], selection via [toggle]/[clearSelection].
class ExplorerController extends AsyncNotifier<ExplorerState> {
  /// Last requested directory — kept across invalidations so ErrorView's
  /// retry lands where the user was (fields survive `invalidateSelf` on the
  /// live element; a disposed/recreated controller starts at root).
  String _path = '';

  /// Authoritative selection (state carries a defensive copy).
  final Set<String> _selected = <String>{};

  String _thumbBase = '';

  @override
  Future<ExplorerState> build() async {
    // Rebuilds on platform switch (new platformPath scope) and profile
    // switch (new thumb base).
    final FsRepository repository = ref.watch(fsRepositoryProvider);
    _thumbBase = ref
        .watch(activeProfileProvider)
        .baseUrl
        .replaceAll(RegExp(r'/+$'), '');
    try {
      final FsRoot root = await repository.fetchRoot();
      if (!root.configured) {
        throw const UnconfiguredSourceException();
      }
      final FsListing listing = await repository.fetchListing(_path);
      return _stateFrom(listing, loading: false);
    } on ValidationException {
      // Contract: fs/list 400 == folder unconfigured.
      throw const UnconfiguredSourceException();
    }
  }

  /// Descend to [path] (`''` returns to the root). The selection is kept;
  /// the previous content stays visible with `loading: true` until the new
  /// listing lands.
  Future<void> navigate(String path) async {
    _path = path;
    final ExplorerState? previous = state.value;
    state = previous != null
        ? AsyncData(previous.copyWith(loading: true))
        : const AsyncLoading<ExplorerState>();
    try {
      final FsListing listing = await ref
          .read(fsRepositoryProvider)
          .fetchListing(path);
      state = AsyncData(_stateFrom(listing, loading: false));
    } on ValidationException {
      state = AsyncError<ExplorerState>(
        const UnconfiguredSourceException(),
        StackTrace.current,
      );
    } catch (error, stackTrace) {
      state = AsyncError<ExplorerState>(error, stackTrace);
    }
  }

  /// Add/remove one file (by name in the open directory) from the
  /// selection.
  void toggle(String name) {
    final ExplorerState? current = state.value;
    if (current == null) {
      return;
    }
    final String rel = current.relPath(name);
    if (!_selected.remove(rel)) {
      _selected.add(rel);
    }
    state = AsyncData(current.copyWith(selected: Set<String>.of(_selected)));
  }

  /// Drop the whole selection (bar action after a save).
  void clearSelection() {
    _selected.clear();
    final ExplorerState? current = state.value;
    if (current != null) {
      state = AsyncData(current.copyWith(selected: <String>{}));
    }
  }

  /// ErrorView's retry: re-runs [build] for [_path] (fields survive the
  /// invalidation on the live element).
  void retry() => ref.invalidateSelf();

  ExplorerState _stateFrom(FsListing listing, {required bool loading}) =>
      ExplorerState(
        path: listing.path,
        segments: listing.segments,
        parent: listing.parent,
        dirs: listing.dirs,
        files: listing.files,
        selected: Set<String>.of(_selected),
        loading: loading,
        thumbBase: _thumbBase,
      );
}
