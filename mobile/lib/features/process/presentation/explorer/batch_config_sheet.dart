import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_flutter/lucide_flutter.dart';

import '../../../../app/theme/tokens.dart';
import '../../../../core/widgets/ghost_button.dart';
import '../../../../core/widgets/label_caps.dart';
import '../../../../core/widgets/primary_button.dart';
import '../../../../core/widgets/toast_exception.dart';
import '../../domain/batch.dart';
import '../../domain/batch_step.dart';
import '../../domain/process_repository.dart';
import '../batch_controller.dart';

/// What the sheet's confirm button does (M4 picker flow).
enum BatchCreateMode {
  /// Create a draft only — no profile required.
  draft,

  /// Create **then** `POST …/queue` — a step profile is required.
  queue,
}

/// Bottom sheet: optional name → media type → step profile → confirm.
///
/// Returns true when the batch was created (and queued, in
/// [BatchCreateMode.queue]); the caller toasts nothing extra and navigates
/// back to `/process`.
Future<bool> showBatchConfigSheet(
  BuildContext context, {
  required BatchCreateMode mode,
  required List<String> files,
}) async {
  final bool? result = await showModalBottomSheet<bool>(
    context: context,
    isScrollControlled: true,
    backgroundColor: AppColors.parchment50,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(AppRadii.md)),
    ),
    builder: (BuildContext sheetContext) => Padding(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(sheetContext).viewInsets.bottom,
      ),
      child: BatchConfigSheet(mode: mode, files: files),
    ),
  );
  return result == true;
}

/// Sheet body — exported so tests can pump it directly (no route needed).
class BatchConfigSheet extends ConsumerStatefulWidget {
  const BatchConfigSheet({super.key, required this.mode, required this.files});

  /// Draft vs. queue (confirm label + validation differ).
  final BatchCreateMode mode;

  /// Source-folder-relative image paths to import.
  final List<String> files;

  @override
  ConsumerState<BatchConfigSheet> createState() => _BatchConfigSheetState();
}

class _BatchConfigSheetState extends ConsumerState<BatchConfigSheet> {
  final TextEditingController _name = TextEditingController();
  String _mediaType = 'raster';
  StepProfile? _profile;
  bool _saving = false;

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final TextTheme textTheme = Theme.of(context).textTheme;
    final AsyncValue<List<StepProfile>> profilesAsync = ref.watch(
      stepProfilesProvider(_mediaType),
    );
    final AsyncValue<StepCatalog> catalogAsync = ref.watch(
      stepCatalogProvider(_mediaType),
    );
    final List<StepProfile>? profiles = profilesAsync.value;
    final bool profilesLoading =
        profilesAsync.isLoading && !profilesAsync.hasValue;

    return SafeArea(
      top: false,
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.lg,
          AppSpacing.lg,
          AppSpacing.lg,
          AppSpacing.xl,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text(
              widget.mode == BatchCreateMode.draft
                  ? 'Save as draft'
                  : 'Queue this batch',
              style: textTheme.titleMedium?.copyWith(
                color: AppColors.ink800,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: AppSpacing.xs),
            Text(
              '${widget.files.length} image${widget.files.length == 1 ? '' : 's'} selected',
              style: textTheme.bodySmall?.copyWith(color: AppColors.ink400),
            ),
            const SizedBox(height: AppSpacing.lg),
            TextField(
              controller: _name,
              decoration: const InputDecoration(
                labelText: 'Batch name (optional)',
                hintText: 'Left empty, the server names it',
              ),
            ),
            const SizedBox(height: AppSpacing.lg),
            const LabelCaps(text: 'Media type'),
            const SizedBox(height: AppSpacing.xs),
            SegmentedButton<String>(
              segments: const <ButtonSegment<String>>[
                ButtonSegment<String>(
                  value: 'raster',
                  label: Text('Raster'),
                  icon: Icon(LucideIcons.images, size: 16),
                ),
                ButtonSegment<String>(
                  value: 'png',
                  label: Text('PNG'),
                  icon: Icon(LucideIcons.scissors, size: 16),
                ),
              ],
              selected: <String>{_mediaType},
              onSelectionChanged: (Set<String> selection) => setState(() {
                _mediaType = selection.first;
                _profile = null; // profiles are per media type.
              }),
            ),
            const SizedBox(height: AppSpacing.lg),
            const LabelCaps(text: 'Step profile'),
            const SizedBox(height: AppSpacing.xs),
            if (profilesLoading)
              Text(
                'Loading profiles…',
                style: textTheme.bodySmall?.copyWith(color: AppColors.ink400),
              )
            else if (profilesAsync.hasError && profiles == null)
              Text(
                processErrorText(profilesAsync.error ?? Exception('unknown')),
                style: textTheme.bodySmall?.copyWith(color: AppColors.rust400),
              )
            else if (profiles == null || profiles.isEmpty)
              Text(
                'No step profiles yet — create one in Config, or save a draft',
                style: textTheme.bodySmall?.copyWith(color: AppColors.ink400),
              )
            else
              DropdownButton<StepProfile>(
                value: _profile,
                isExpanded: true,
                hint: Text(
                  'Choose a profile',
                  style: textTheme.bodyMedium?.copyWith(
                    color: AppColors.ink400,
                  ),
                ),
                style: textTheme.bodyMedium?.copyWith(color: AppColors.ink800),
                dropdownColor: AppColors.parchment200,
                items: <DropdownMenuItem<StepProfile>>[
                  for (final StepProfile profile in profiles)
                    DropdownMenuItem<StepProfile>(
                      value: profile,
                      child: Text(
                        profile.name,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                ],
                onChanged: (StepProfile? value) =>
                    setState(() => _profile = value),
              ),
            if (widget.mode == BatchCreateMode.queue &&
                _profile == null &&
                (profiles?.isNotEmpty ?? false)) ...<Widget>[
              const SizedBox(height: AppSpacing.xs),
              Text(
                'Select a profile to queue this batch.',
                style: textTheme.bodySmall?.copyWith(color: AppColors.rust400),
              ),
            ],
            const SizedBox(height: AppSpacing.xl),
            Row(
              children: <Widget>[
                GhostButton(
                  label: 'Cancel',
                  onPressed: () => Navigator.of(context).pop(false),
                ),
                const Spacer(),
                _confirmButton(catalogAsync),
              ],
            ),
          ],
        ),
      ),
    );
  }

  /// Confirm keeps its label but dims + ignores taps until the mode's
  /// requirements hold (draft: a profile or a loaded/failed catalog;
  /// queue: a profile — per [BatchCreateMode] contract).
  Widget _confirmButton(AsyncValue<StepCatalog> catalog) {
    final Widget button = PrimaryButton(
      label: widget.mode == BatchCreateMode.draft
          ? 'Save draft'
          : 'Queue batch',
      loading: _saving,
      onPressed: _submit,
    );
    if (_saving || _ready(catalog)) {
      return button;
    }
    return Opacity(opacity: 0.5, child: IgnorePointer(child: button));
  }

  bool _ready(AsyncValue<StepCatalog> catalog) {
    if (_profile != null) {
      return true;
    }
    if (widget.mode == BatchCreateMode.queue) {
      return false;
    }
    // Draft without a profile builds its steps from the catalog (the
    // backend rejects an empty step list); while it loads the button waits,
    // an *errored* catalog is allowed through so the 400 detail surfaces as
    // a toast instead of a permanently dead button.
    return catalog.hasValue || !catalog.isLoading;
  }

  Future<void> _submit() async {
    if (_saving) {
      return;
    }
    setState(() => _saving = true);
    try {
      final ProcessPickerRepository repository = ref.read(
        processPickerProvider,
      );
      final Batch batch = await repository.createBatch(
        name: _name.text.trim(),
        mediaType: _mediaType,
        steps: _buildSteps(),
        profileId: _profile?.id,
        files: widget.files,
      );
      if (widget.mode == BatchCreateMode.queue) {
        await repository.queueBatch(batch.id);
      }
      if (!mounted) {
        return;
      }
      showAppToast(
        context,
        widget.mode == BatchCreateMode.draft ? 'Draft saved' : 'Queued',
        tone: ToastTone.success,
      );
      Navigator.of(context).pop(true);
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() => _saving = false);
      showAppToast(context, actionErrorText(error), tone: ToastTone.error);
    }
  }

  /// Profile → its steps untouched (the wizard sends them the same way);
  /// no profile → the full catalog order as a runnable default (the
  /// backend 400s an empty step list).
  List<BatchStep> _buildSteps() {
    final StepProfile? profile = _profile;
    if (profile != null) {
      return profile.steps;
    }
    final StepCatalog? catalog = ref
        .read(stepCatalogProvider(_mediaType))
        .value;
    if (catalog == null) {
      return const <BatchStep>[];
    }
    return <BatchStep>[
      for (final String key in catalog.order) BatchStep(key: key),
    ];
  }
}
