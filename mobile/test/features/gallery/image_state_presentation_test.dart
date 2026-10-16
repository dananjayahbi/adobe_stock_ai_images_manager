import 'package:flutter_test/flutter_test.dart';

import 'package:ai_stock_studio/core/widgets/stamp_badge.dart';
import 'package:ai_stock_studio/core/widgets/status_chip.dart';
import 'package:ai_stock_studio/features/gallery/domain/image_record.dart';
import 'package:ai_stock_studio/features/gallery/presentation/image_state_presentation.dart';

void main() {
  group('stateLabel covers the full contract', () {
    test('every canonical state has its human label', () {
      expect(stateLabel('COLLECTED'), 'Collected');
      expect(stateLabel('APPROVED'), 'Approved');
      expect(stateLabel('REJECTED'), 'Rejected');
      expect(stateLabel('READY_TO_PUBLISH'), 'Ready to publish');
      expect(stateLabel('PUBLISHED'), 'Published');
      expect(stateLabel('AS_ACCEPTED'), 'AS Accepted');
    });

    test('labels cover every kImageStates entry exactly', () {
      final List<String> labels = kImageStates
          .map<String>(stateLabel)
          .toList(growable: false);
      expect(labels, <String>[
        'Collected',
        'Approved',
        'Rejected',
        'Ready to publish',
        'Published',
        'AS Accepted',
      ]);
      expect(labels.toSet(), hasLength(labels.length)); // no collisions
    });

    test('an unknown state falls back to the raw value, never a throw', () {
      expect(stateLabel('FUTURE_STATE'), 'FUTURE_STATE');
      expect(stateTone('FUTURE_STATE'), StampTone.neutral);
    });
  });

  group('stateTone maps lifecycle to the tone palette', () {
    test('contract tones', () {
      expect(stateTone('COLLECTED'), StampTone.neutral);
      expect(stateTone('APPROVED'), StampTone.success);
      expect(stateTone('REJECTED'), StampTone.failure);
      expect(stateTone('READY_TO_PUBLISH'), StampTone.accent);
      expect(stateTone('PUBLISHED'), StampTone.success);
      expect(stateTone('AS_ACCEPTED'), StampTone.success);
    });

    test('chip twin mirrors the stamp palette', () {
      expect(stateChipTone('APPROVED'), StatusTone.success);
      expect(stateChipTone('REJECTED'), StatusTone.failure);
      expect(stateChipTone('READY_TO_PUBLISH'), StatusTone.accent);
      expect(stateChipTone('COLLECTED'), StatusTone.neutral);
    });
  });

  group('flags present', () {
    test('labels cover the display-order contract', () {
      expect(kImageFlags, <String>[
        'QUARANTINED',
        'USED',
        'UNUSED',
        'METADATA_READY',
        'INCOMPATIBLE',
        'REFINED',
        'UPSCALED',
        'OCR_REJECTED',
      ]);
      expect(flagLabel('QUARANTINED'), 'Quarantined');
      expect(flagLabel('USED'), 'Used');
      expect(flagLabel('UNUSED'), 'Unused');
      expect(flagLabel('METADATA_READY'), 'Metadata ready');
      expect(flagLabel('INCOMPATIBLE'), 'Incompatible');
      expect(flagLabel('REFINED'), 'Refined');
      expect(flagLabel('UPSCALED'), 'Upscaled');
      expect(flagLabel('OCR_REJECTED'), 'OCR rejected');
    });

    test('tones: quarantine warning, incompatibilities failure, used '
        'accent, unused neutral, metadata ready success', () {
      expect(flagTone('QUARANTINED'), StampTone.warning);
      expect(flagTone('INCOMPATIBLE'), StampTone.failure);
      expect(flagTone('OCR_REJECTED'), StampTone.failure);
      expect(flagTone('USED'), StampTone.accent);
      expect(flagTone('UNUSED'), StampTone.neutral);
      expect(flagTone('METADATA_READY'), StampTone.success);
      expect(flagTone('REFINED'), StampTone.accent);
      expect(flagTone('UPSCALED'), StampTone.accent);
      expect(flagTone('SOMETHING_NEW'), StampTone.neutral);
    });

    test('every flag carries a non-null icon for its chip', () {
      for (final String flag in kImageFlags) {
        expect(flagIcon(flag), isNotNull, reason: flag);
        expect(flagChipTone(flag), isA<StatusTone>(), reason: flag);
      }
    });
  });
}
