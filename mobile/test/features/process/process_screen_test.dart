import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:ai_stock_studio/app/theme/theme.dart';
import 'package:ai_stock_studio/core/utils/app_exception.dart';
import 'package:ai_stock_studio/core/widgets/error_view.dart';
import 'package:ai_stock_studio/features/process/domain/batch.dart';
import 'package:ai_stock_studio/features/process/domain/batch_step.dart';
import 'package:ai_stock_studio/features/process/domain/process_repository.dart';
import 'package:ai_stock_studio/features/process/presentation/process_screen.dart';
import 'package:ai_stock_studio/features/settings/data/profile_store.dart';

/// Scriptable list backend: only `fetchBatches` matters on this screen.
class _FakeProcessRepository implements ProcessRepository {
  BatchList list = const BatchList(items: <Batch>[], total: 0);
  Object? listError;
  int fetchCalls = 0;

  @override
  Future<BatchList> fetchBatches({int limit = 50}) async {
    fetchCalls += 1;
    final Object? error = listError;
    if (error != null) {
      throw error; // ignore: only_throw_errors — fake failure injection
    }
    return list;
  }

  @override
  Future<BatchDetail> fetchBatchDetail(String batchId) async =>
      throw UnimplementedError();

  @override
  Stream<BatchSnapshot> watchBatch(String batchId) =>
      throw UnimplementedError();

  @override
  Future<Batch> runBatch(String batchId) async => throw UnimplementedError();

  @override
  Future<StepCatalog> fetchStepCatalog({String? mediaType}) async =>
      throw UnimplementedError();

  @override
  Future<Batch> createBatch({
    required String name,
    required String mediaType,
    required List<BatchStep> steps,
    String? profileId,
  }) async =>
      throw UnimplementedError();

  @override
  Future<Batch> cancelBatch(String batchId) async => throw UnimplementedError();

  @override
  Future<void> deleteBatch(String batchId) async => throw UnimplementedError();

  @override
  Future<List<StepProfile>> fetchProfiles({String? mediaType}) async =>
      throw UnimplementedError();

  @override
  Future<StepProfile> createProfile({
    required String name,
    required String mediaType,
    required List<BatchStep> steps,
  }) async =>
      throw UnimplementedError();
}

Batch _batch() => Batch(
      id: 'b-1',
      name: 'Alpha run',
      mediaType: 'raster',
      steps: const <BatchStep>[BatchStep(key: 'ocr')],
      profileId: null,
      status: 'completed',
      stepProgress: null,
      error: null,
      recordCount: 4,
      createdAt: DateTime(2026, 10, 13, 13, 38),
      updatedAt: DateTime(2026, 10, 13, 14, 2),
      finishedAt: null,
    );

void main() {
  setUpAll(() {
    GoogleFonts.config.allowRuntimeFetching = false;
    SharedPreferences.setMockInitialValues({});
  });

  Future<void> pumpProcess(
    WidgetTester tester,
    _FakeProcessRepository repo,
  ) async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          processRepositoryProvider.overrideWithValue(repo),
          sharedPreferencesProvider.overrideWithValue(prefs),
        ],
        child: MaterialApp(
          theme: buildAppTheme(),
          home: const ProcessScreen(),
        ),
      ),
    );
  }

  /// Settles async provider work without waiting on infinite animations.
  Future<void> settle(WidgetTester tester) async {
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
  }

  testWidgets('a failed pull-to-refresh keeps the stale rows and pins an '
      'inline retry (05 §3)', (WidgetTester tester) async {
    final _FakeProcessRepository repo = _FakeProcessRepository()
      ..list = BatchList(items: <Batch>[_batch()], total: 1);
    await pumpProcess(tester, repo);
    await settle(tester);
    expect(find.text('Alpha run'), findsOneWidget);
    expect(find.byType(ErrorView), findsNothing);

    // Server hiccup on refresh: rows stay, the failure surfaces inline.
    repo.listError = const ServerException(message: 'boom');
    await tester.fling(
      find.byType(ListView),
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
    expect(find.text('Alpha run'), findsOneWidget); // stale row retained
    expect(find.text('The studio server hit an error. Please try again.'), findsOneWidget);

    // Retry reconnects and clears the inline error.
    repo.listError = null;
    await tester.ensureVisible(find.text('Retry'));
    await tester.pump();
    await tester.tap(find.text('Retry'));
    await settle(tester);

    expect(find.byType(ErrorView), findsNothing);
    expect(find.text('Alpha run'), findsOneWidget);
    expect(repo.fetchCalls, 3); // load + failed refresh + retry
  });
}
