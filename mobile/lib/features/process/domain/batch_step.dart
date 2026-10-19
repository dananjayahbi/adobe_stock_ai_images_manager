/// Step-level entities for the batch pipeline (02 §6): `BatchStep`,
/// `StepProgress`, the `GET /api/batches/steps` catalog, and
/// `StepProfile` from `/api/step-profiles`.
///
/// Model map (backend `batches.py` / `step_profiles.py` / `pipeline_defs.py`):
/// * [BatchStep] ← one `steps[i]` entry `{key, config}` (also a
///   `profile.steps[i]` and one `POST` body step).
/// * [StepProgress] ← one `step_progress[key]` value `{status, message,
///   counts}` written live by the runner.
/// * [StepCatalog] ← `GET /api/batches/steps` `{order, steps, media_types}`.
/// * [StepDefinition] ← one catalog `steps[i]` (label/description/defaults).
/// * [StepProfile] ← `ProfileResponse` (`GET/POST /api/step-profiles`).
class BatchStep {
  const BatchStep({required this.key, this.config = const <String, Object?>{}});

  factory BatchStep.fromJson(Map<String, Object?> json) {
    final Object? raw = json['config'];
    final Map<String, Object?> config = raw is Map<Object?, Object?>
        ? raw.map<String, Object?>(
            (Object? k, Object? v) =>
                MapEntry<String, Object?>(k?.toString() ?? '', v),
          )
        : <String, Object?>{};
    return BatchStep(key: json['key']?.toString() ?? '', config: config);
  }

  /// Catalog key (`upscale`, `bg_remove`, `ocr`, …).
  final String key;

  /// Step config — backend normalises unknown keys away and merges the rest
  /// over `default_config`, so an empty map is a valid "all defaults" step.
  final Map<String, Object?> config;
}

/// Per-step live state under `BatchResponse.step_progress[key]`:
/// `{status, message, counts}`. `counts` mirrors the runner's job counters
/// (`succeeded/failed/skipped/pending/running`).
class StepProgress {
  const StepProgress({
    required this.status,
    required this.message,
    this.counts,
  });

  factory StepProgress.fromJson(Map<String, Object?> json) {
    final Object? rawCounts = json['counts'];
    final Map<String, int>? counts = rawCounts is Map<Object?, Object?>
        ? rawCounts.map<String, int>(
            (Object? k, Object? v) => MapEntry<String, int>(
              k?.toString() ?? '',
              v is num ? v.toInt() : 0,
            ),
          )
        : null;
    return StepProgress(
      status: json['status']?.toString() ?? 'pending',
      message: json['message']?.toString() ?? '',
      counts: counts,
    );
  }

  /// `status` — `pending|running|completed|failed|cancelled`.
  final String status;

  /// `message` — runner summary; the backend already folds counts into it
  /// (web renders it verbatim).
  final String message;

  /// `counts` — `{succeeded, failed, skipped, pending, running}` or null.
  final Map<String, int>? counts;
}

/// One entry of the `GET /api/batches/steps` catalog payload
/// (`pipeline_defs.step_payload`).
class StepDefinition {
  const StepDefinition({
    required this.key,
    required this.label,
    required this.description,
    required this.mediaTypes,
    required this.defaultConfig,
  });

  factory StepDefinition.fromJson(Map<String, Object?> json) {
    final List<String> mediaTypes = <String>[];
    final Object? rawTypes = json['media_types'];
    if (rawTypes is List<Object?>) {
      for (final Object? type in rawTypes) {
        if (type is String) {
          mediaTypes.add(type);
        }
      }
    }
    final Object? rawDefaults = json['default_config'];
    return StepDefinition(
      key: json['key']?.toString() ?? '',
      label: json['label']?.toString() ?? '',
      description: json['description']?.toString() ?? '',
      mediaTypes: mediaTypes,
      defaultConfig: rawDefaults is Map<Object?, Object?>
          ? rawDefaults.map<String, Object?>(
              (Object? k, Object? v) =>
                  MapEntry<String, Object?>(k?.toString() ?? '', v),
            )
          : <String, Object?>{},
    );
  }

  /// `key`.
  final String key;

  /// `label` — human name shown in the timeline/wizard.
  final String label;

  /// `description` — one-line blurb.
  final String description;

  /// `media_types` — which batch kinds may include this step.
  final List<String> mediaTypes;

  /// `default_config` — the defaults a bare `{key, config:{}}` runs with.
  final Map<String, Object?> defaultConfig;
}

/// `GET /api/batches/steps[?media_type=raster|png]` →
/// `{order, steps, media_types}`. `order` is the canonical run order and
/// `media_types` maps each kind to its pickable keys.
class StepCatalog {
  const StepCatalog({required this.order, required this.steps});

  factory StepCatalog.fromJson(Map<String, Object?> json) {
    final List<String> order = <String>[];
    final Object? rawOrder = json['order'];
    if (rawOrder is List<Object?>) {
      for (final Object? key in rawOrder) {
        if (key is String) {
          order.add(key);
        }
      }
    }
    final List<StepDefinition> steps = <StepDefinition>[];
    final Object? rawSteps = json['steps'];
    if (rawSteps is List<Object?>) {
      for (final Object? row in rawSteps) {
        if (row is Map<Object?, Object?>) {
          steps.add(
            StepDefinition.fromJson(
              row.map<String, Object?>(
                (Object? k, Object? v) =>
                    MapEntry<String, Object?>(k?.toString() ?? '', v),
              ),
            ),
          );
        }
      }
    }
    return StepCatalog(order: order, steps: steps);
  }

  /// `order` — canonical step order across all kinds.
  final List<String> order;

  /// `steps` — definitions (already media-filtered when the query was).
  final List<StepDefinition> steps;

  /// Label lookup for the timeline; unknown keys fall back to the raw key.
  String labelFor(String key) {
    for (final StepDefinition step in steps) {
      if (step.key == key) {
        return step.label.isEmpty ? key : step.label;
      }
    }
    return key;
  }

  /// Description lookup; unknown keys → empty.
  String descriptionFor(String key) {
    for (final StepDefinition step in steps) {
      if (step.key == key) {
        return step.description;
      }
    }
    return '';
  }
}

/// `ProfileResponse` — a saved, reusable step recipe
/// (`GET/POST /api/step-profiles`).
class StepProfile {
  const StepProfile({
    required this.id,
    required this.name,
    required this.mediaType,
    required this.steps,
  });

  factory StepProfile.fromJson(Map<String, Object?> json) {
    final List<BatchStep> steps = <BatchStep>[];
    final Object? rawSteps = json['steps'];
    if (rawSteps is List<Object?>) {
      for (final Object? row in rawSteps) {
        if (row is Map<Object?, Object?>) {
          steps.add(
            BatchStep.fromJson(
              row.map<String, Object?>(
                (Object? k, Object? v) =>
                    MapEntry<String, Object?>(k?.toString() ?? '', v),
              ),
            ),
          );
        }
      }
    }
    return StepProfile(
      id: json['id']?.toString() ?? '',
      name: json['name']?.toString() ?? '',
      mediaType: json['media_type']?.toString() ?? 'raster',
      steps: steps,
    );
  }

  /// `id`.
  final String id;

  /// `name`.
  final String name;

  /// `media_type` — `raster` | `png`.
  final String mediaType;

  /// `steps` — the saved recipe.
  final List<BatchStep> steps;
}
