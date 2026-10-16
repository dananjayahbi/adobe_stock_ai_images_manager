import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path_provider/path_provider.dart';

import '../../../core/utils/app_exception.dart';
import '../../platforms/presentation/platforms_controller.dart';
import '../data/delivery_repository_impl.dart';
import '../domain/delivery_item.dart';
import '../domain/delivery_repository.dart';

/// Seam between "the server sent bytes" and "the file exists on disk":
/// the controller downloads via the repository and saves through this
/// provider, so widget tests inject a fake writer instead of mocking
/// path_provider.
typedef SaveExportFile = Future<String> Function(String fileName, List<int> bytes);

final saveExportFileProvider = Provider<SaveExportFile>((ref) => saveExportToDownloads);

/// Default saver: `<documents>/downloads/<fileName>`, never overwriting an
/// earlier export (`name (1).csv`, `name (2).csv`, …).
Future<String> saveExportToDownloads(String fileName, List<int> bytes) async {
  final Directory documents = await getApplicationDocumentsDirectory();
  final Directory downloads = Directory(
    '${documents.path}${Platform.pathSeparator}downloads',
  );
  await downloads.create(recursive: true);

  File target = File('${downloads.path}${Platform.pathSeparator}$fileName');
  int attempt = 1;
  while (await target.exists()) {
    final int dot = fileName.lastIndexOf('.');
    final String stem = dot > 0 ? fileName.substring(0, dot) : fileName;
    final String extension = dot > 0 ? fileName.substring(dot) : '';
    target = File(
      '${downloads.path}${Platform.pathSeparator}$stem ($attempt)$extension',
    );
    attempt += 1;
  }
  await target.writeAsBytes(bytes, flush: true);
  return target.path;
}

/// Which delivery action is currently in flight (drives per-row spinners
/// and blocks overlapping runs).
enum DeliveryAction { none, preview, csv, zip, force }

/// Composed screen state (05 §2.8): the delivery rows from
/// `GET /api/records`, the latest CSV preview (the "deliverable set"
/// summary), the user's selection, filter chips, the session-local export
/// history, and the offline flag that disables the action cards.
///
/// Seam note: there is **no** delivery *list* endpoint — 02 §7 is all
/// mutations/exports whose bodies demand `record_ids`, so the id-bearing
/// list comes from the records listing (documented in the M4 report).
class DeliveryState {
  const DeliveryState({
    this.candidates = const <DeliveryCandidate>[],
    this.preview,
    this.exports = const <ExportRecord>[],
    this.selection = const <String>{},
    this.filter = DeliveryFilter.all,
    this.offline = false,
    this.busy = DeliveryAction.none,
  });

  final List<DeliveryCandidate> candidates;
  final CsvPreview? preview;
  final List<ExportRecord> exports;
  final Set<String> selection;
  final DeliveryFilter filter;

  /// True once an action/fetch failed with a network error; cleared by the
  /// next success. Drives the offline note + disabled action cards.
  final bool offline;

  final DeliveryAction busy;

  /// Rows under the active filter chip.
  List<DeliveryCandidate> get visibleCandidates =>
      candidates.where(filter.accepts).toList();

  int get selectedCount => selection.length;

  /// Deliverable-set size for the summary — the server's own CSV row count
  /// when a preview has landed, else a client-side estimate.
  int get deliverableCount =>
      preview?.rowCount ?? candidates.where((DeliveryCandidate c) => c.deliverable).length;

  bool get isEmpty => candidates.isEmpty && (preview?.rowCount ?? 0) == 0;

  DeliveryState copyWith({
    List<DeliveryCandidate>? candidates,
    CsvPreview? preview,
    List<ExportRecord>? exports,
    Set<String>? selection,
    DeliveryFilter? filter,
    bool? offline,
    DeliveryAction? busy,
  }) =>
      DeliveryState(
        candidates: candidates ?? this.candidates,
        preview: preview ?? this.preview,
        exports: exports ?? this.exports,
        selection: selection ?? this.selection,
        filter: filter ?? this.filter,
        offline: offline ?? this.offline,
        busy: busy ?? this.busy,
      );
}

/// Riverpod's default exponential auto-retry would hide a failure behind
/// up to ten silent re-fetches; delivery failures surface immediately as
/// the screen's ErrorView + manual retry (same policy as gallery).
Duration? _noRetry(int retryCount, Object error) => null;

/// `/delivery` controller (05 §2.8): loads rows + preview once, keeps the
/// selection across refreshes, and runs the four actions. Failures rethrow
/// so the screen can toast `uiMessageFor`, after the state has already
/// recorded offline/busy transitions.
final deliveryControllerProvider =
    AsyncNotifierProvider<DeliveryController, DeliveryState>(
  DeliveryController.new,
  retry: _noRetry,
);

class DeliveryController extends AsyncNotifier<DeliveryState> {
  /// Backend cap for one delivery ZIP (`delivery.py MAX_ZIP_FILES`).
  static const int maxBundleFiles = 50;

  DeliveryRepository get _repository => ref.read(deliveryRepositoryProvider);

  String get _platformId => ref.read(activePlatformIdProvider);

  Set<String> get _selection =>
      state.value?.selection ?? const <String>{};

  /// `null` = "every eligible record"; an explicit selection rides along
  /// (web parity — see `DeliveryRepository`).
  List<String>? get _selectedIds =>
      _selection.isEmpty ? null : _selection.toList();

  @override
  Future<DeliveryState> build() async {
    // Platform switch → fresh fetch through the new platformPath prefix.
    ref.watch(activePlatformIdProvider);
    final List<Object> results = await Future.wait<Object>(
      <Future<Object>>[
        _repository.fetchCandidates(_platformId),
        _repository.previewCsv(_platformId),
      ],
    );
    return DeliveryState(
      candidates: results[0] as List<DeliveryCandidate>,
      preview: results[1] as CsvPreview,
    );
  }

  /// Pull-to-refresh (05: gestures): refetch rows + preview, keep the
  /// selection (minus rows that vanished) and stale data on failure. The
  /// error still rethrows so the screen can toast it.
  Future<void> refresh() async {
    final DeliveryState? current = state.value;
    try {
      final List<DeliveryCandidate> candidates =
          await _repository.fetchCandidates(_platformId);
      final Set<String> kept = (current?.selection ?? const <String>{})
          .where((String id) => candidates.any((DeliveryCandidate c) => c.id == id))
          .toSet();
      final CsvPreview preview = await _repository.previewCsv(_platformId);
      state = AsyncData<DeliveryState>(
        (current ?? const DeliveryState()).copyWith(
          candidates: candidates,
          preview: preview,
          selection: kept,
          offline: false,
        ),
      );
    } catch (error, stackTrace) {
      final DeliveryState? latest = state.value;
      if (latest == null) {
        state = AsyncError<DeliveryState>(error, stackTrace);
      } else {
        state = AsyncData<DeliveryState>(
          latest.copyWith(offline: error is NetworkException),
        );
      }
      rethrow;
    }
  }

  void setFilter(DeliveryFilter filter) {
    final DeliveryState? current = state.value;
    if (current == null || current.filter == filter) return;
    state = AsyncData<DeliveryState>(current.copyWith(filter: filter));
  }

  void toggleRecord(String id) {
    final DeliveryState? current = state.value;
    if (current == null) return;
    final Set<String> next = Set<String>.of(current.selection);
    if (!next.remove(id)) next.add(id);
    state = AsyncData<DeliveryState>(current.copyWith(selection: next));
  }

  void clearSelection() {
    final DeliveryState? current = state.value;
    if (current == null || current.selection.isEmpty) return;
    state = AsyncData<DeliveryState>(current.copyWith(selection: const <String>{}));
  }

  /// Fresh preview for the action sheet — selection-aware, and stored back
  /// into the state so the summary row count follows it.
  Future<CsvPreview> previewForAction() {
    final String platformId = _platformId;
    return _runAction(DeliveryAction.preview, () async {
      final CsvPreview preview = await _repository.previewCsv(
        platformId,
        recordIds: _selectedIds,
      );
      _write(_requireValue.copyWith(preview: preview));
      return preview;
    });
  }

  /// `POST csv` → save through [saveExportFileProvider] → history entry.
  /// Returns the on-device path for the success toast.
  Future<String> exportCsv() {
    final String platformId = _platformId;
    return _runAction(DeliveryAction.csv, () async {
      final DeliveryFile file = await _repository.exportCsv(
        platformId,
        recordIds: _selectedIds,
      );
      final String path =
          await ref.read(saveExportFileProvider)(file.fileName, file.bytes);
      _recordExport(file, path, ExportKind.csv);
      return path;
    });
  }

  /// `POST bundle` → save → history. Caps are enforced before the request
  /// so a doomed upload never leaves the device (web parity).
  Future<String> bundleZip() async {
    final List<String> ids = _selection.toList();
    if (ids.isEmpty) {
      throw const ValidationException(
        message: 'Select the rows to bundle first.',
      );
    }
    if (ids.length > maxBundleFiles) {
      throw const ValidationException(
        message: 'A bundle holds at most $maxBundleFiles files — '
            'narrow the selection.',
      );
    }
    final String platformId = _platformId;
    return _runAction(DeliveryAction.zip, () async {
      final DeliveryFile file = await _repository.bundleZip(
        platformId,
        recordIds: ids,
      );
      final String path =
          await ref.read(saveExportFileProvider)(file.fileName, file.bytes);
      _recordExport(file, path, ExportKind.zip);
      return path;
    });
  }

  /// `POST force-accept` with the dialog's reason → counts for the toast,
  /// then a quiet row refresh (accepted stages moved server-side).
  Future<ForceAcceptOutcome> forceAccept(String reason) async {
    final String clean = reason.trim();
    if (clean.isEmpty) {
      throw const ValidationException(
        message: 'A reason is required to force-accept.',
      );
    }
    final List<String> ids = _selection.toList();
    if (ids.isEmpty) {
      throw const ValidationException(
        message: 'Select the rows to force-accept first.',
      );
    }
    final String platformId = _platformId;
    final ForceAcceptOutcome outcome = await _runAction(
      DeliveryAction.force,
      () => _repository.forceAccept(
        platformId,
        recordIds: ids,
        reason: clean,
      ),
    );
    // Best-effort: a failed re-fetch must not mask the outcome the user
    // just earned — it only flips the offline note.
    try {
      final List<DeliveryCandidate> candidates =
          await _repository.fetchCandidates(platformId);
      _write(_requireValue.copyWith(candidates: candidates));
    } on NetworkException {
      _write(_requireValue.copyWith(offline: true));
    } catch (_) {
      // Keep the stale rows; the toast already reports the real result.
    }
    return outcome;
  }

  DeliveryState get _requireValue =>
      state.value ?? const DeliveryState();

  void _write(DeliveryState next) => state = AsyncData<DeliveryState>(next);

  /// Runs one action with the busy flag up and the offline flag following
  /// the network truth; every failure rethrows with its original stack.
  Future<T> _runAction<T>(DeliveryAction action, Future<T> Function() body) async {
    if (_requireValue.busy != DeliveryAction.none) {
      throw const ValidationException(
        message: 'Another delivery action is still running.',
      );
    }
    _write(_requireValue.copyWith(busy: action));
    try {
      final T result = await body();
      _write(_requireValue.copyWith(busy: DeliveryAction.none, offline: false));
      return result;
    } catch (error) {
      _write(
        _requireValue.copyWith(
          busy: DeliveryAction.none,
          offline: error is NetworkException,
        ),
      );
      rethrow;
    }
  }

  void _recordExport(DeliveryFile file, String path, ExportKind kind) {
    final List<ExportRecord> history = <ExportRecord>[
      ExportRecord(
        fileName: file.fileName,
        savedPath: path,
        byteCount: file.bytes.length,
        kind: kind,
        exportedAt: DateTime.now(),
      ),
      ..._requireValue.exports,
    ];
    _write(
      _requireValue.copyWith(
        exports: history.length > 10 ? history.sublist(0, 10) : history,
      ),
    );
  }
}
