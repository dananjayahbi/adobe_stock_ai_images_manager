import 'delivery_item.dart';

/// Delivery endpoints (02 §7 + the `GET /api/records` list that supplies
/// record ids — §7 has no id-bearing list of its own).
///
/// Every method takes the active `platformId` so paths go through
/// `platformPath` (03 §3.5). Implementations live in `data/`; the screen
/// depends only on this contract so widget tests can fake the backend via
/// `deliveryRepositoryProvider`.
///
/// Selection semantics follow web parity
/// (`frontend-new/src/lib/delivery.ts`): an explicit selection travels as
/// `{record_ids: [...], only_ready: false}` — the operator picked those
/// exact rows — while "no selection" means the whole deliverable set as
/// `{record_ids: null, only_ready: true}`.
abstract class DeliveryRepository {
  /// `GET /api/records?limit=500` — the delivery list: ids for selection,
  /// filenames/stages for the status section and filter chips.
  Future<List<DeliveryCandidate>> fetchCandidates(String platformId);

  /// `POST /api/assets/csv/preview` — CSV text + warnings, no side effects.
  Future<CsvPreview> previewCsv(
    String platformId, {
    List<String>? recordIds,
  });

  /// `POST /api/assets/csv` — Adobe CSV bytes pinned to the server's
  /// `Content-Disposition` filename (409 `detail` when nothing is exportable).
  Future<DeliveryFile> exportCsv(
    String platformId, {
    List<String>? recordIds,
  });

  /// `POST /api/assets/bundle` — ZIP of the selected images plus their CSV.
  /// Backend caps the archive at 50 files (`MAX_ZIP_FILES`) and demands an
  /// explicit, non-empty selection.
  Future<DeliveryFile> bundleZip(
    String platformId, {
    required List<String> recordIds,
  });

  /// `POST /api/assets/force-accept` — `{record_ids[], reason}` → counts of
  /// accepted/refused rows (a refused row keeps its explanation).
  Future<ForceAcceptOutcome> forceAccept(
    String platformId, {
    required List<String> recordIds,
    required String reason,
  });

  /// `POST /api/assets/rename-suggest` — dry run: what the batch's names
  /// would become (nothing is written).
  Future<RenameOutcome> suggestNames(
    String platformId, {
    required List<RenameEntry> items,
    bool regenerate = false,
  });

  /// `POST /api/assets/apply-suggested-names` — adopt the model's names.
  Future<RenameOutcome> applySuggestedNames(
    String platformId, {
    required List<RenameEntry> items,
    bool regenerate = false,
  });

  /// `POST /api/assets/rename` — set explicit names (slugified server-side;
  /// a blank name clears the override back to the derived name).
  Future<RenameOutcome> rename(
    String platformId, {
    required List<RenameEntry> items,
    bool regenerate = false,
  });
}
