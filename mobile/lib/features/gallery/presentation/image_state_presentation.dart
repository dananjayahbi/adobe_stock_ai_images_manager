import 'package:flutter/material.dart';
import 'package:lucide_flutter/lucide_flutter.dart';

import '../../../core/widgets/stamp_badge.dart';
import '../../../core/widgets/status_chip.dart';

/// State / flag presenters shared by the gallery chrome, tiles, sheet and
/// action bar (05 §2.5–2.6).
///
/// One source of truth for the human labels and the tone families over the
/// `state`/`flags` contract; raw values are never rendered by these
/// helpers — unknown backend values fall back to the raw string
/// ([stateLabel] / [flagLabel]) and a neutral tone, so a new value can
/// never crash a screen.

/// Human label for one image state ('Collected', 'Ready to publish', …).
String stateLabel(String state) => switch (state) {
  'COLLECTED' => 'Collected',
  'APPROVED' => 'Approved',
  'REJECTED' => 'Rejected',
  'READY_TO_PUBLISH' => 'Ready to publish',
  'PUBLISHED' => 'Published',
  'AS_ACCEPTED' => 'AS Accepted',
  _ => state,
};

/// Stamp tone for a state: collected neutral, approved/published accepted
/// (success), rejected failure, queued accent.
StampTone stateTone(String state) => switch (state) {
  'APPROVED' || 'PUBLISHED' || 'AS_ACCEPTED' => StampTone.success,
  'REJECTED' => StampTone.failure,
  'READY_TO_PUBLISH' => StampTone.accent,
  _ => StampTone.neutral,
};

/// [stateTone] as the chip palette's equivalent (StatusChip twin).
StatusTone stateChipTone(String state) => _chipTone(stateTone(state));

/// Human label for one flag ('Metadata ready', 'OCR rejected', …).
String flagLabel(String flag) => switch (flag) {
  'QUARANTINED' => 'Quarantined',
  'USED' => 'Used',
  'UNUSED' => 'Unused',
  'METADATA_READY' => 'Metadata ready',
  'INCOMPATIBLE' => 'Incompatible',
  'REFINED' => 'Refined',
  'UPSCALED' => 'Upscaled',
  'OCR_REJECTED' => 'OCR rejected',
  _ => flag,
};

/// Stamp tone for a flag: quarantine warning, incompatibility failures,
/// used accent, unused neutral, metadata ready success, refinements
/// accent-ish, unknown neutral.
StampTone flagTone(String flag) => switch (flag) {
  'QUARANTINED' => StampTone.warning,
  'INCOMPATIBLE' || 'OCR_REJECTED' => StampTone.failure,
  'USED' => StampTone.accent,
  'METADATA_READY' => StampTone.success,
  'REFINED' || 'UPSCALED' => StampTone.accent,
  _ => StampTone.neutral,
};

/// [flagTone] as the chip palette's equivalent.
StatusTone flagChipTone(String flag) => _chipTone(flagTone(flag));

/// Icon paired with a flag chip (never color alone — 04 §4 rule 1).
IconData flagIcon(String flag) => switch (flag) {
  'QUARANTINED' => LucideIcons.shieldAlert,
  'USED' => LucideIcons.circleCheck,
  'UNUSED' => LucideIcons.circle,
  'METADATA_READY' => LucideIcons.fileCheck,
  'INCOMPATIBLE' => LucideIcons.triangleAlert,
  'REFINED' => LucideIcons.wand2,
  'UPSCALED' => LucideIcons.maximize,
  'OCR_REJECTED' => LucideIcons.scanText,
  _ => LucideIcons.tags,
};

StatusTone _chipTone(StampTone tone) => switch (tone) {
  StampTone.success => StatusTone.success,
  StampTone.warning => StatusTone.warning,
  StampTone.failure => StatusTone.failure,
  StampTone.accent => StatusTone.accent,
  StampTone.neutral => StatusTone.neutral,
};
