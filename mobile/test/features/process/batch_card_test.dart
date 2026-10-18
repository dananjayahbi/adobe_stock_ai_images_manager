import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:ai_stock_studio/app/theme/theme.dart';
import 'package:ai_stock_studio/core/widgets/stamp_badge.dart';
import 'package:ai_stock_studio/core/widgets/status_chip.dart';
import 'package:ai_stock_studio/features/process/domain/batch.dart';
import 'package:ai_stock_studio/features/process/domain/batch_step.dart';
import 'package:ai_stock_studio/features/process/presentation/batch_card.dart';

Batch _batch({String status = 'queued'}) => Batch(
  id: 'b-1',
  name: 'Queue me',
  mediaType: 'raster',
  steps: const <BatchStep>[BatchStep(key: 'ocr')],
  profileId: null,
  status: status,
  stepProgress: null,
  error: null,
  recordCount: 3,
  createdAt: DateTime(2026, 10, 17, 8),
  updatedAt: DateTime(2026, 10, 17, 8),
  finishedAt: null,
  queuedAt: DateTime(2026, 10, 17, 8, 30),
);

void main() {
  setUpAll(() {
    GoogleFonts.config.allowRuntimeFetching = false;
    SharedPreferences.setMockInitialValues({});
  });

  Future<void> pumpCard(
    WidgetTester tester, {
    Batch? batch,
    int? queuePosition,
  }) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: buildAppTheme(),
        home: Scaffold(
          body: BatchCard(
            batch: batch ?? _batch(),
            queuePosition: queuePosition,
            onTap: () {},
          ),
        ),
      ),
    );
    await tester.pump();
  }

  testWidgets('queued batch stamps the accent tone, reads Queued and shows its '
      'queue position chip', (WidgetTester tester) async {
    await pumpCard(tester, queuePosition: 2);

    final StampBadge badge = tester.widget<StampBadge>(find.byType(StampBadge));
    expect(badge.label, 'QUEUED');
    expect(badge.tone, StampTone.accent); // brass/on-deck family
    expect(find.text('QUEUED'), findsOneWidget); // stamp renders uppercase

    final StatusChip chip = tester.widget<StatusChip>(find.byType(StatusChip));
    expect(chip.label, '#2');
    expect(chip.tone, StatusTone.accent);
    expect(find.text('#2'), findsOneWidget);
  });

  testWidgets('no queue position → no position chip', (
    WidgetTester tester,
  ) async {
    await pumpCard(tester, batch: _batch(status: 'draft'));

    expect(find.byType(StatusChip), findsNothing);
    expect(find.text('#'), findsNothing);
    final StampBadge badge = tester.widget<StampBadge>(find.byType(StampBadge));
    expect(badge.tone, StampTone.neutral); // drafts stay neutral
    expect(find.text('DRAFT'), findsOneWidget);
  });

  test('tone map keeps running accent and terminal stamps per contract', () {
    expect(BatchCard.toneFor('running'), StampTone.accent);
    expect(BatchCard.toneFor('queued'), StampTone.accent);
    expect(BatchCard.toneFor('completed'), StampTone.success);
    expect(BatchCard.toneFor('failed'), StampTone.failure);
    expect(BatchCard.toneFor('draft'), StampTone.neutral);
    expect(BatchCard.toneFor('cancelled'), StampTone.neutral);
  });

  test('label map prints every status as caps — completed reads PROCESSED', () {
    expect(BatchCard.labelFor('draft'), 'DRAFT');
    expect(BatchCard.labelFor('queued'), 'QUEUED');
    expect(BatchCard.labelFor('running'), 'RUNNING');
    expect(BatchCard.labelFor('completed'), 'PROCESSED'); // 02 §1
    expect(BatchCard.labelFor('failed'), 'FAILED');
    expect(BatchCard.labelFor('cancelled'), 'CANCELLED');
  });

  testWidgets('a completed batch stamps PROCESSED with the success tone', (
    WidgetTester tester,
  ) async {
    await pumpCard(tester, batch: _batch(status: 'completed'));

    final StampBadge badge = tester.widget<StampBadge>(find.byType(StampBadge));
    expect(badge.label, 'PROCESSED');
    expect(badge.tone, StampTone.success);
    expect(find.text('PROCESSED'), findsOneWidget);
    expect(find.text('COMPLETED'), findsNothing); // raw status never prints
  });
}
