import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:ai_stock_studio/app/theme/theme.dart';
import 'package:ai_stock_studio/core/utils/app_exception.dart';
import 'package:ai_stock_studio/core/widgets/error_view.dart';
import 'package:ai_stock_studio/core/widgets/empty_state.dart';
import 'package:ai_stock_studio/core/widgets/ghost_button.dart';
import 'package:ai_stock_studio/core/widgets/primary_button.dart';
import 'package:ai_stock_studio/core/widgets/skeleton_loader.dart';
import 'package:ai_stock_studio/features/delivery/data/delivery_repository_impl.dart';
import 'package:ai_stock_studio/features/delivery/domain/delivery_item.dart';
import 'package:ai_stock_studio/features/delivery/domain/delivery_repository.dart';
import 'package:ai_stock_studio/features/delivery/presentation/delivery_controller.dart';
import 'package:ai_stock_studio/features/delivery/presentation/delivery_screen.dart';
import 'package:ai_stock_studio/features/delivery/presentation/delivery_widgets.dart';
import 'package:ai_stock_studio/features/settings/data/profile_store.dart';

/// Fake backend: scriptable values + call counters; the repository provider
/// is overridden directly, so Dio and path_provider never run. Saving goes
/// through [saveExportFileProvider]'s seam, also overridden below.
class FakeDeliveryRepository implements DeliveryRepository {
  List<DeliveryCandidate> candidatesValue = <DeliveryCandidate>[
    const DeliveryCandidate(
      id: 'row-1',
      filename: 'Wire_loop_trimming_tool_2K.jpg',
      stage: 'METADATA_READY',
      uploadFilename: 'sculpting-tool-with-wooden-handle-and-wire-loop.jpg',
      title: 'Sculpting tool with wooden handle and wire loop',
      isUsed: true,
    ),
    const DeliveryCandidate(
      id: 'row-2',
      filename: 'Acoustic_guitar_bridge_pins.jpg',
      stage: 'METADATA_READY',
      uploadFilename: 'six-cream-acoustic-guitar-bridge-pins.jpg',
      title: 'Six Cream Acoustic Guitar Bridge Pins',
    ),
  ];

  CsvPreview previewValue = const CsvPreview(
    csvText: 'Filename,Title,Keywords,Category,Releases\r\n'
        'sculpting-tool.jpg,Sculpting tool,"wire, loop",10,\r\n'
        'bridge-pins.jpg,Guitar bridge pins,"cream, pins",12,\r\n',
    rowCount: 2,
  );

  DeliveryFile csvFile = const DeliveryFile(
    fileName: 'adobe-stock-metadata.csv',
    bytes: <int>[1, 2, 3],
  );
  DeliveryFile zipFile = const DeliveryFile(
    fileName: 'adobe-stock-delivery.zip',
    bytes: <int>[9, 9],
  );
  ForceAcceptOutcome forceValue = const ForceAcceptOutcome(
    items: <ForceAcceptItem>[],
    accepted: 1,
    refused: 0,
  );

  Object? candidatesError;
  Object? previewError;
  Object? forceError;

  /// When set, every fetch awaits it — drives the loading-state test.
  Completer<void>? gate;

  int candidatesCalls = 0;
  int previewCalls = 0;
  int exportCalls = 0;
  int bundleCalls = 0;
  int forceCalls = 0;
  List<String>? lastForceIds;
  String? lastForceReason;

  Future<T> _run<T>(Future<T> Function() body, Object? error) async {
    final Completer<void>? pending = gate;
    if (pending != null) await pending.future;
    if (error != null) throw error; // ignore: only_throw_errors — fake failure
    return body();
  }

  @override
  Future<List<DeliveryCandidate>> fetchCandidates(String platformId) {
    candidatesCalls += 1;
    return _run(() async => candidatesValue, candidatesError);
  }

  @override
  Future<CsvPreview> previewCsv(String platformId, {List<String>? recordIds}) {
    previewCalls += 1;
    return _run(() async => previewValue, previewError);
  }

  @override
  Future<DeliveryFile> exportCsv(String platformId, {List<String>? recordIds}) {
    exportCalls += 1;
    return _run(() async => csvFile, null);
  }

  @override
  Future<DeliveryFile> bundleZip(
    String platformId, {
    required List<String> recordIds,
  }) {
    bundleCalls += 1;
    return _run(() async => zipFile, null);
  }

  @override
  Future<ForceAcceptOutcome> forceAccept(
    String platformId, {
    required List<String> recordIds,
    required String reason,
  }) {
    forceCalls += 1;
    lastForceIds = recordIds;
    lastForceReason = reason;
    return _run(() async => forceValue, forceError);
  }

  @override
  Future<RenameOutcome> suggestNames(
    String platformId, {
    required List<RenameEntry> items,
    bool regenerate = false,
  }) async =>
      const RenameOutcome(items: <RenameResultItem>[], updated: 0, failed: 0);

  @override
  Future<RenameOutcome> applySuggestedNames(
    String platformId, {
    required List<RenameEntry> items,
    bool regenerate = false,
  }) async =>
      const RenameOutcome(items: <RenameResultItem>[], updated: 0, failed: 0);

  @override
  Future<RenameOutcome> rename(
    String platformId, {
    required List<RenameEntry> items,
    bool regenerate = false,
  }) async =>
      const RenameOutcome(items: <RenameResultItem>[], updated: 0, failed: 0);
}

void main() {
  setUpAll(() {
    // Never hit fonts.google.com from tests (03 §5).
    GoogleFonts.config.allowRuntimeFetching = false;
    SharedPreferences.setMockInitialValues({});
    // Haptics (destructive confirms) never complete under flutter_test
    // without a responder for SystemChannels.platform — ack them all.
    TestWidgetsFlutterBinding.ensureInitialized();
    TestWidgetsFlutterBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, (call) async => null);
  });

  /// Save seam: records exist only in the fake repo; the writer just names
  /// the on-device path the success toast will show.
  Future<String> fakeSave(String fileName, List<int> bytes) async =>
      'C:\\app\\documents\\downloads\\$fileName';

  Future<void> pumpDelivery(
    WidgetTester tester,
    FakeDeliveryRepository repo,
  ) async {
    final SharedPreferences storage = await SharedPreferences.getInstance();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          deliveryRepositoryProvider.overrideWithValue(repo),
          sharedPreferencesProvider.overrideWithValue(storage),
          saveExportFileProvider.overrideWithValue(fakeSave),
        ],
        child: MaterialApp(
          theme: buildAppTheme(),
          home: const DeliveryScreen(),
        ),
      ),
    );
  }

  /// Settles async provider work without waiting on infinite animations.
  Future<void> settle(WidgetTester tester) async {
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
  }

  /// Lets the 3 s toast timer fire so no test ends on a pending timer.
  Future<void> clearToasts(WidgetTester tester) async {
    await tester.pump(const Duration(seconds: 3));
    await tester.pump(const Duration(milliseconds: 100));
  }

  Future<void> openForceAccept(WidgetTester tester) async {
    await tester.ensureVisible(find.text('Force-accept'));
    await tester.pump();
    await tester.tap(find.text('Force-accept'));
    await tester.pumpAndSettle();
  }

  /// Selects the first delivery row — the row list runs below the fold on
  /// an 800×600 test surface, so scroll it into view first.
  Future<void> selectFirstRow(WidgetTester tester) async {
    final Finder first = find.byType(Checkbox).first;
    await tester.ensureVisible(first);
    await tester.pump();
    await tester.tap(first);
    await tester.pump(const Duration(milliseconds: 100));
  }

  TextButton confirmButton(WidgetTester tester) => tester.widget<TextButton>(
        find.widgetWithText(TextButton, 'Force-accept'),
      );

  testWidgets('loading shows three action-card skeletons, then rows + summary',
      (WidgetTester tester) async {
    final FakeDeliveryRepository repo = FakeDeliveryRepository()
      ..gate = Completer<void>();
    await pumpDelivery(tester, repo);

    expect(find.text('Delivery'), findsOneWidget);
    expect(find.byType(SkeletonLoader), findsWidgets);
    expect(find.text('CSV preview & export'), findsNothing);

    repo.gate!.complete();
    await settle(tester);

    expect(find.byType(SkeletonLoader), findsNothing);
    expect(find.text('CSV preview & export'), findsOneWidget);
    expect(find.text('ZIP bundle'), findsOneWidget);
    expect(find.text('Force-accept'), findsOneWidget);
    // Summary comes from the CSV preview row count (02 §7).
    expect(find.text('2 rows ready for Adobe'), findsOneWidget);
    expect(find.text('2 records · 0 selected'), findsOneWidget);
    expect(find.text('ALL'), findsOneWidget);
    // Rows render their delivery filename + stage chip.
    expect(
      find.text('sculpting-tool-with-wooden-handle-and-wire-loop.jpg'),
      findsOneWidget,
    );
    expect(find.text('METADATA_READY'), findsNWidgets(2));
  });

  testWidgets('empty deliverable set shows the 05 empty state', (
    WidgetTester tester,
  ) async {
    final FakeDeliveryRepository repo = FakeDeliveryRepository()
      ..candidatesValue = <DeliveryCandidate>[]
      ..previewValue = const CsvPreview(csvText: '', rowCount: 0);
    await pumpDelivery(tester, repo);
    await settle(tester);

    expect(find.text('Nothing to deliver yet'), findsOneWidget);
    expect(find.text('Open gallery'), findsOneWidget);
    expect(find.byType(EmptyState), findsOneWidget);
    expect(find.text('CSV preview & export'), findsNothing);
  });

  testWidgets('fetch failure → inline ErrorView, retry recovers', (
    WidgetTester tester,
  ) async {
    final FakeDeliveryRepository repo = FakeDeliveryRepository()
      ..candidatesError = const ServerException(message: 'boom');
    await pumpDelivery(tester, repo);
    await settle(tester);

    expect(find.byType(ErrorView), findsOneWidget);
    expect(
      find.text('The studio server hit an error. Please try again.'),
      findsOneWidget,
    );
    expect(find.text('CSV preview & export'), findsNothing);

    repo.candidatesError = null;
    await tester.ensureVisible(find.text('Retry'));
    await tester.pump();
    await tester.tap(find.text('Retry'));
    await settle(tester);

    expect(find.byType(ErrorView), findsNothing);
    expect(find.text('CSV preview & export'), findsOneWidget);
  });

  testWidgets('force-accept dialog demands a reason; cancel never calls the '
      'repository', (WidgetTester tester) async {
    final FakeDeliveryRepository repo = FakeDeliveryRepository();
    await pumpDelivery(tester, repo);
    await settle(tester);

    await selectFirstRow(tester);
    await openForceAccept(tester);

    expect(find.text('Force-accept 1 record?'), findsOneWidget);
    expect(find.byType(TextField), findsOneWidget);
    expect(confirmButton(tester).onPressed, isNull); // empty reason blocks

    await tester.enterText(find.byType(TextField), '   ');
    await tester.pump();
    expect(confirmButton(tester).onPressed, isNull); // whitespace blocks too

    await tester.enterText(find.byType(TextField), 'score disputed the gate');
    await tester.pump();
    expect(confirmButton(tester).onPressed, isNotNull);

    await tester.tap(find.widgetWithText(GhostButton, 'Cancel'));
    await tester.pumpAndSettle();
    expect(find.byType(TextField), findsNothing);
    expect(repo.forceCalls, 0);
  });

  testWidgets('force-accept confirm posts {ids, reason} and toasts the '
      'accepted/refused counts', (WidgetTester tester) async {
    final FakeDeliveryRepository repo = FakeDeliveryRepository();
    await pumpDelivery(tester, repo);
    await settle(tester);

    await selectFirstRow(tester);
    await openForceAccept(tester);

    await tester.enterText(find.byType(TextField), 'score disputed the gate');
    await tester.pump();
    await tester.tap(find.widgetWithText(TextButton, 'Force-accept'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 450));

    expect(repo.forceCalls, 1);
    expect(repo.lastForceIds, <String>['row-1']);
    expect(repo.lastForceReason, 'score disputed the gate');
    expect(find.text('Force-accepted 1 · refused 0'), findsOneWidget);
    await clearToasts(tester);
  });

  testWidgets('CSV card → preview sheet → Export saves and toasts the path',
      (WidgetTester tester) async {
    final FakeDeliveryRepository repo = FakeDeliveryRepository();
    await pumpDelivery(tester, repo);
    await settle(tester);

    await tester.ensureVisible(find.text('CSV preview & export'));
    await tester.pump();
    await tester.tap(find.text('CSV preview & export'));
    await tester.pumpAndSettle();

    expect(find.text('CSV PREVIEW'), findsOneWidget);
    expect(find.text('2 rows · 0 warnings · 0 skipped'), findsOneWidget);
    expect(find.textContaining('Filename,Title,Keywords'), findsOneWidget);

    await tester.tap(find.widgetWithText(PrimaryButton, 'Export CSV'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 450));

    expect(repo.exportCalls, 1);
    expect(
      find.text(
        'Saved to C:\\app\\documents\\downloads\\adobe-stock-metadata.csv',
      ),
      findsOneWidget,
    );
    expect(find.text('CSV PREVIEW'), findsNothing); // sheet closed
    await clearToasts(tester);
  });

  testWidgets('ZIP bundle needs a selection, saves, and lands in history '
      'with the EXPORTED stamp', (WidgetTester tester) async {
    final FakeDeliveryRepository repo = FakeDeliveryRepository();
    await pumpDelivery(tester, repo);
    await settle(tester);

    // No selection yet → client-side validation toast, no request.
    await tester.ensureVisible(find.text('ZIP bundle'));
    await tester.pump();
    await tester.tap(find.text('ZIP bundle'));
    await tester.pump(const Duration(milliseconds: 450));
    expect(repo.bundleCalls, 0);
    expect(find.text('Select the rows to bundle first.'), findsOneWidget);
    await clearToasts(tester);

    await selectFirstRow(tester);
    expect(find.text('1 selected · images + matching CSV (max 50).'),
        findsOneWidget);

    await tester.ensureVisible(find.text('ZIP bundle'));
    await tester.pump();
    await tester.tap(find.text('ZIP bundle'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 450));

    expect(repo.bundleCalls, 1);
    expect(
      find.text('Saved to C:\\app\\documents\\downloads\\adobe-stock-delivery.zip'),
      findsOneWidget,
    );
    expect(find.text('RECENT EXPORTS'), findsOneWidget);
    expect(find.text('EXPORTED'), findsOneWidget);
    await clearToasts(tester);
  });

  testWidgets('network failure during an action pins the offline note and '
      'disables the action cards', (WidgetTester tester) async {
    final FakeDeliveryRepository repo = FakeDeliveryRepository()
      ..forceError = const NetworkException(message: 'link down');
    await pumpDelivery(tester, repo);
    await settle(tester);

    await selectFirstRow(tester);
    await openForceAccept(tester);
    await tester.enterText(find.byType(TextField), 'offline attempt');
    await tester.pump();
    await tester.tap(find.widgetWithText(TextButton, 'Force-accept'));
    await tester.pump(const Duration(milliseconds: 450));

    expect(find.textContaining('Offline — actions disabled'), findsOneWidget);
    expect(
      find.text("Can't reach the studio server. Check your network and "
          'connection profile.'),
      findsOneWidget,
    );

    final ActionCard csvCard = tester.widget<ActionCard>(
      find.byWidgetPredicate(
        (Widget w) => w is ActionCard && w.title == 'CSV preview & export',
      ),
    );
    expect(csvCard.enabled, isFalse);

    // Disabled tap opens nothing.
    await tester.ensureVisible(find.text('CSV preview & export'));
    await tester.pump();
    await tester.tap(find.text('CSV preview & export'));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('CSV PREVIEW'), findsNothing);
    await clearToasts(tester);
  });

  testWidgets('pull-to-refresh re-fetches the delivery status', (
    WidgetTester tester,
  ) async {
    final FakeDeliveryRepository repo = FakeDeliveryRepository();
    await pumpDelivery(tester, repo);
    await settle(tester);
    expect(repo.candidatesCalls, 1);

    await tester.fling(
      find.byType(CustomScrollView),
      const Offset(0, 300),
      1000,
    );
    await tester.pump(); // gesture starts
    await tester.pump(const Duration(seconds: 1)); // indicator snaps in
    await tester.pump(const Duration(seconds: 1)); // refresh runs
    await tester.pump(const Duration(seconds: 1)); // indicator exits
    await settle(tester);

    expect(repo.candidatesCalls, 2);
    expect(repo.previewCalls, 2);
  });

  testWidgets('refresh failure pins an inline retry over the stale rows '
      '(05 §3)', (WidgetTester tester) async {
    final FakeDeliveryRepository repo = FakeDeliveryRepository();
    await pumpDelivery(tester, repo);
    await settle(tester);
    expect(repo.candidatesCalls, 1);

    // A server-side failure on pull-to-refresh: rows stay, inline error
    // appears with Retry — no toast-only dead end.
    repo.candidatesError = const ServerException(message: 'boom');
    await tester.fling(
      find.byType(CustomScrollView),
      const Offset(0, 300),
      1000,
    );
    await tester.pump(); // gesture starts
    await tester.pump(const Duration(seconds: 1)); // indicator snaps in
    await tester.pump(const Duration(seconds: 1)); // refresh fails
    await tester.pump(const Duration(seconds: 1)); // indicator exits
    await settle(tester);

    expect(find.byType(ErrorView), findsOneWidget);
    expect(find.text('Retry'), findsOneWidget);
    expect(
      find.text('The studio server hit an error. Please try again.'),
      findsOneWidget, // inline copy for the failed refresh
    );
    expect(
      find.text('2 rows ready for Adobe'),
      findsOneWidget, // stale summary retained above/below the error
    );

    // Retry reconnects and clears the inline error.
    repo.candidatesError = null;
    await tester.ensureVisible(find.text('Retry'));
    await tester.pump();
    await tester.tap(find.text('Retry'));
    await settle(tester);

    expect(find.byType(ErrorView), findsNothing);
    expect(repo.candidatesCalls, greaterThan(1));
  });
}
