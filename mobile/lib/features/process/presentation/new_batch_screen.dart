import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:lucide_flutter/lucide_flutter.dart';

import '../../../app/theme/tokens.dart';
import '../../../core/widgets/app_card.dart';
import '../../../core/widgets/error_view.dart';
import '../../../core/widgets/ghost_button.dart';
import '../../../core/widgets/label_caps.dart';
import '../../../core/widgets/primary_button.dart';
import '../../../core/widgets/skeleton_loader.dart';
import '../../../core/widgets/toast_exception.dart';
import '../domain/batch.dart';
import '../domain/batch_step.dart';
import '../domain/process_repository.dart';
import 'batch_controller.dart';

/// `/process/new` (top-level, tabs hidden) — the 3-step New batch wizard,
/// parity with web `NewBatchModal.tsx`: **type → profile-or-custom →
/// steps** → `POST /api/batches` (draft) → replace with `/process/:id`.
/// * Step 1: media type (raster photos / transparent PNGs).
/// * Step 2: saved profiles (`GET /api/step-profiles`) or Custom pipeline;
///   a chosen profile **skips** the steps step (web rule).
/// * Step 3 (custom only): toggle catalog steps in canonical run order.
///   Config forms are **omitted in MVP** — bare `{key, config:{}}` steps run
///   on backend defaults (config editing lands later, 05 §2.7.2).
class NewBatchScreen extends ConsumerStatefulWidget {
  const NewBatchScreen({super.key});

  @override
  ConsumerState<NewBatchScreen> createState() => _NewBatchScreenState();
}

class _NewBatchScreenState extends ConsumerState<NewBatchScreen> {
  int _step = 0;
  String? _mediaType;
  StepProfile? _profile;
  final Set<String> _enabled = <String>{};
  bool _creating = false;
  String? _stepError;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('New batch')),
      body: Column(
        children: <Widget>[
          Expanded(child: _currentStep(context)),
          _footer(context),
        ],
      ),
    );
  }

  Widget _currentStep(BuildContext context) => switch (_step) {
        0 => _typeStep(context),
        1 => _profileStep(context),
        _ => _stepPicker(context),
      };

  // ---------------------------------------------------------------- step 1

  Widget _typeStep(BuildContext context) => ListView(
        padding: const EdgeInsets.all(AppSpacing.md),
        children: <Widget>[
          Text(
            'What are we processing?',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: AppSpacing.xs),
          Text(
            'Pick the media type this batch handles.',
            style: Theme.of(context)
                .textTheme
                .bodySmall
                ?.copyWith(color: AppColors.ink400),
          ),
          const SizedBox(height: AppSpacing.md),
          _ChoiceCard(
            icon: LucideIcons.images,
            title: 'Raster photos',
            subtitle: 'JPG/WEBP photos · white-background pipeline',
            onTap: () => _chooseType('raster'),
          ),
          const SizedBox(height: AppSpacing.sm),
          _ChoiceCard(
            icon: LucideIcons.scissors,
            title: 'Transparent PNGs',
            subtitle: 'Cut-outs · background-removal pipeline',
            onTap: () => _chooseType('png'),
          ),
        ],
      );

  void _chooseType(String mediaType) {
    setState(() {
      _mediaType = mediaType;
      _profile = null;
      _enabled.clear();
      _step = 1;
    });
  }

  // ---------------------------------------------------------------- step 2

  Widget _profileStep(BuildContext context) {
    final String mediaType = _mediaType ?? 'raster';
    final AsyncValue<List<StepProfile>> profilesAsync =
        ref.watch(stepProfilesProvider(mediaType));
    if (profilesAsync.isLoading && !profilesAsync.hasValue) {
      return _skeletons();
    }
    final List<StepProfile>? profiles = profilesAsync.value;
    if (profiles == null) {
      return ErrorView(
        message: processErrorText(profilesAsync.error ?? Exception('unknown')),
        onRetry: () => ref.invalidate(stepProfilesProvider(mediaType)),
      );
    }
    return ListView(
      padding: const EdgeInsets.all(AppSpacing.md),
      children: <Widget>[
        Text(
          'How should it run?',
          style: Theme.of(context).textTheme.titleLarge,
        ),
        const SizedBox(height: AppSpacing.xs),
        Text(
          'Reuse a saved profile or build a custom pipeline.',
          style: Theme.of(context)
              .textTheme
              .bodySmall
              ?.copyWith(color: AppColors.ink400),
        ),
        const SizedBox(height: AppSpacing.md),
        _ChoiceCard(
          icon: LucideIcons.workflow,
          title: 'Custom pipeline',
          subtitle: 'Pick the steps yourself',
          onTap: () => setState(() {
            _profile = null;
            _step = 2;
          }),
        ),
        const SizedBox(height: AppSpacing.sm),
        const LabelCaps(text: 'Saved profiles'),
        const SizedBox(height: AppSpacing.xs),
        if (profiles.isEmpty)
          Text(
            'No saved profiles yet.',
            style: Theme.of(context)
                .textTheme
                .bodySmall
                ?.copyWith(color: AppColors.ink400),
          ),
        for (final StepProfile profile in profiles) ...<Widget>[
          const SizedBox(height: AppSpacing.xs),
          _ChoiceCard(
            icon: LucideIcons.listChecks,
            title: profile.name,
            subtitle: '${profile.steps.length} steps',
            selected: _profile?.id == profile.id,
            onTap: () => setState(() => _profile = profile),
          ),
        ],
      ],
    );
  }

  // ---------------------------------------------------------------- step 3

  Widget _stepPicker(BuildContext context) {
    final String mediaType = _mediaType ?? 'raster';
    final AsyncValue<StepCatalog> catalogAsync =
        ref.watch(stepCatalogProvider(mediaType));
    if (catalogAsync.isLoading && !catalogAsync.hasValue) {
      return _skeletons();
    }
    final StepCatalog? catalog = catalogAsync.value;
    if (catalog == null) {
      return ErrorView(
        message: processErrorText(catalogAsync.error ?? Exception('unknown')),
        onRetry: () => ref.invalidate(stepCatalogProvider(mediaType)),
      );
    }
    final List<StepDefinition> options = <StepDefinition>[];
    for (final String key in catalog.order) {
      for (final StepDefinition def in catalog.steps) {
        if (def.key != key) {
          continue;
        }
        final bool fits =
            def.mediaTypes.isEmpty || def.mediaTypes.contains(mediaType);
        if (fits) {
          options.add(def);
        }
      }
    }
    return ListView(
      padding: const EdgeInsets.all(AppSpacing.md),
      children: <Widget>[
        Text('Which steps?', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: AppSpacing.xs),
        Text(
          'Runs top-to-bottom in this order. Config defaults for MVP.',
          style: Theme.of(context)
              .textTheme
              .bodySmall
              ?.copyWith(color: AppColors.ink400),
        ),
        if (_stepError != null) ...<Widget>[
          const SizedBox(height: AppSpacing.sm),
          Text(
            _stepError!,
            style: Theme.of(context)
                .textTheme
                .bodySmall
                ?.copyWith(color: AppColors.rust400),
          ),
        ],
        const SizedBox(height: AppSpacing.sm),
        for (final StepDefinition def in options)
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            dense: true,
            title: Text(def.label),
            subtitle: def.description.isEmpty
                ? null
                : Text(
                    def.description,
                    style: Theme.of(context)
                        .textTheme
                        .bodySmall
                        ?.copyWith(color: AppColors.ink400),
                  ),
            value: _enabled.contains(def.key),
            onChanged: (bool on) => setState(() {
              if (on) {
                _enabled.add(def.key);
              } else {
                _enabled.remove(def.key);
              }
              _stepError = null;
            }),
          ),
      ],
    );
  }

  // --------------------------------------------------------------- footer

  Widget _footer(BuildContext context) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Row(
            children: <Widget>[
              if (_step > 0)
                GhostButton(
                  label: 'Back',
                  onPressed: () => setState(() => _step -= 1),
                ),
              const Spacer(),
              if (_step >= 1)
                PrimaryButton(
                  label: 'Create batch',
                  loading: _creating,
                  onPressed: _step == 1 && _profile == null
                      ? null
                      : _create,
                ),
            ],
          ),
        ),
      );

  Future<void> _create() async {
    if (_creating || _mediaType == null) {
      return;
    }
    if (_step == 2 && _enabled.isEmpty) {
      setState(() => _stepError = 'Pick at least one step.');
      return;
    }
    setState(() {
      _creating = true;
      _stepError = null;
    });
    try {
      final Batch batch = await ref.read(processRepositoryProvider).createBatch(
            // Empty name → backend default ("Raster photos · timestamp",
            // web parity: NewBatchModal sends no name).
            name: '',
            mediaType: _mediaType!,
            steps: _buildSteps(),
            profileId: _profile?.id,
          );
      if (!mounted) {
        return;
      }
      showAppToast(context, 'Batch created', tone: ToastTone.success);
      context.pushReplacement('/process/${batch.id}');
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() => _creating = false);
      showAppToast(context, processErrorText(error), tone: ToastTone.error);
    }
  }

  /// Profile → the profile's steps ride along untouched; custom → the
  /// enabled keys in **canonical catalog order** (backend merges
  /// `default_config` over the empty configs).
  List<BatchStep> _buildSteps() {
    final StepProfile? profile = _profile;
    if (profile != null) {
      return profile.steps;
    }
    final StepCatalog? catalog =
        ref.read(stepCatalogProvider(_mediaType ?? 'raster')).value;
    final List<String> order = catalog?.order ?? _enabled.toList();
    return <BatchStep>[
      for (final String key in order)
        if (_enabled.contains(key)) BatchStep(key: key),
    ];
  }

  Widget _skeletons() => ListView(
        padding: const EdgeInsets.all(AppSpacing.md),
        children: const <Widget>[
          SkeletonLoader(height: 72),
          SkeletonLoader(height: 72),
          SkeletonLoader(height: 72),
        ],
      );
}

/// Selectable wizard card (media type, custom pipeline, saved profile).
class _ChoiceCard extends StatelessWidget {
  const _ChoiceCard({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
    this.selected = false,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;
  final bool selected;

  @override
  Widget build(BuildContext context) => AppCard(
        padding: EdgeInsets.zero,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(AppRadii.md),
          child: Container(
            padding: const EdgeInsets.all(AppSpacing.md),
            decoration: BoxDecoration(
              border: Border.all(
                color: selected ? AppColors.brass400 : Colors.transparent,
                width: 2,
              ),
              borderRadius: BorderRadius.circular(AppRadii.md),
            ),
            child: Row(
              children: <Widget>[
                Icon(icon, color: selected ? AppColors.brass400 : AppColors.ink400),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(title, style: Theme.of(context).textTheme.titleSmall),
                      const SizedBox(height: AppSpacing.xs),
                      Text(
                        subtitle,
                        style: Theme.of(context)
                            .textTheme
                            .bodySmall
                            ?.copyWith(color: AppColors.ink400),
                      ),
                    ],
                  ),
                ),
                if (selected)
                  Icon(LucideIcons.circleCheck, color: AppColors.brass400),
              ],
            ),
          ),
        ),
      );
}
