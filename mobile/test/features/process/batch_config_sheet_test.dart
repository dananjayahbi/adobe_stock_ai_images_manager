import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:ai_stock_studio/app/theme/theme.dart';
import 'package:ai_stock_studio/core/utils/app_exception.dart';
import 'package:ai_stock_studio/features/process/domain/batch.dart';
import 'package:ai_stock_studio/features/process/domain/batch_step.dart';
import 'package:ai_stock_studio/features/process/domain/process_repository.dart';
import 'package:ai_stock_studio/features/process/presentation/explorer/batch_config_sheet.dart';
import 'package:ai_stock_studio/features/settings/data/profile_store.dart';

/// Scriptable picker backend implementing the **extended** contract the
/// sheet runs through `processPickerProvider` (create + queue, ordered).
class _FakePickerRepository implements ProcessPickerRepository {
  final List<String> calls = <String>[];
  List<String>? lastFiles;
  String? lastName;
  String? lastMediaType;
  String? lastProfileId;
  List<BatchStep>? lastSteps;

  List<StepProfile> profiles = const <StepProfile>[
    StepProfile(
      id: 'pr-1',
      name: 'Raster presets',
      mediaType: 'raster',
      steps: <BatchStep>[BatchStep(key: 'ocr')],
    ),
  ];
  Object? createError;

  @override
  Future<Batch> createBatch({
    required String name,
    required String mediaType,
    required List<BatchStep> steps,
    String? profileId,
    List<String>? files,
  }) async {
    calls.add('create');
    lastName = name;
    lastMediaType = mediaType;
    lastSteps = steps;
    lastProfileId = profileId;
    lastFiles = files;
    final Object? error = createError;
    if (error != null) {
      throw error; // ignore: only_throw_errors — fake failure injection
    }
    return _batch('b-new', 'draft');
  }

  @override
  Future<Batch> queueBatch(String batchId) async {
    calls.add('queue');
    return _batch(batchId, 'queued');
  }

  @override
  Future<StepCatalog> fetchStepCatalog({String? mediaType}) async =>
      const StepCatalog(
        order: <String>['ocr', 'metadata'],
        steps: <StepDefinition>[],
      );

  @override
  Future<List<StepProfile>> fetchProfiles({String? mediaType}) async => profiles
      .where(
        (StepProfile profile) => profile.mediaType == (mediaType ?? 'raster'),
      )
      .toList();

  @override
  Future<BatchList> fetchBatches({int limit = 50}) async =>
      throw UnimplementedError();

  @override
  Future<BatchDetail> fetchBatchDetail(String batchId) async =>
      throw UnimplementedError();

  @override
  Stream<BatchSnapshot> watchBatch(String batchId) =>
      throw UnimplementedError();

  @override
  Future<Batch> runBatch(String batchId) async => throw UnimplementedError();

  @override
  Future<Batch> cancelBatch(String batchId) async => throw UnimplementedError();

  @override
  Future<void> deleteBatch(String batchId) async => throw UnimplementedError();

  @override
  Future<StepProfile> createProfile({
    required String name,
    required String mediaType,
    required List<BatchStep> steps,
  }) async => throw UnimplementedError();
}

Batch _batch(String id, String status) => Batch(
  id: id,
  name: 'Batch',
  mediaType: 'raster',
  steps: const <BatchStep>[BatchStep(key: 'ocr')],
  profileId: null,
  status: status,
  stepProgress: null,
  error: null,
  recordCount: 2,
  createdAt: DateTime(2026, 10, 17, 9),
  updatedAt: DateTime(2026, 10, 17, 9),
  finishedAt: null,
  queuedAt: status == 'queued' ? DateTime(2026, 10, 17, 9) : null,
);

void main() {
  setUpAll(() {
    GoogleFonts.config.allowRuntimeFetching = false;
    SharedPreferences.setMockInitialValues({});
  });

  /// Opens the sheet through a host button — no GoRouter involved, so the
  /// confirm flow (create / queue / toast) is what gets asserted.
  Future<void> openSheet(
    WidgetTester tester,
    _FakePickerRepository repo, {
    required BatchCreateMode mode,
    required List<String> files,
  }) async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          processRepositoryProvider.overrideWithValue(repo),
          sharedPreferencesProvider.overrideWithValue(prefs),
        ],
        child: MaterialApp(
          theme: buildAppTheme(),
          home: Builder(
            builder: (BuildContext context) => Scaffold(
              body: TextButton(
                onPressed: () =>
                    showBatchConfigSheet(context, mode: mode, files: files),
                child: const Text('open sheet'),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('open sheet'));
    await tester.pumpAndSettle();
  }

  /// Lets a toast's 3 s timer fire so no test ends on a pending timer.
  Future<void> clearToast(WidgetTester tester) async {
    await tester.pump(const Duration(seconds: 3));
    await tester.pump(const Duration(milliseconds: 100));
  }

  testWidgets('Draft confirm creates a draft with the selected files', (
    WidgetTester tester,
  ) async {
    final _FakePickerRepository repo = _FakePickerRepository();
    await openSheet(
      tester,
      repo,
      mode: BatchCreateMode.draft,
      files: <String>['a.jpg', 'sub/b.jpg'],
    );

    expect(find.text('Save draft'), findsOneWidget);
    expect(find.text('2 images selected'), findsOneWidget);

    await tester.ensureVisible(find.text('Save draft'));
    await tester.pump();
    await tester.tap(find.text('Save draft'));
    await tester.pumpAndSettle();

    expect(repo.calls, <String>['create']); // draft never queues
    expect(repo.lastFiles, <String>['a.jpg', 'sub/b.jpg']);
    expect(repo.lastMediaType, 'raster'); // default segmented value
    expect(repo.lastName, ''); // empty → server default name
    expect(repo.lastProfileId, isNull);
    // No profile chosen → default steps come from the catalog.
    expect(repo.lastSteps?.map((BatchStep step) => step.key), <String>[
      'ocr',
      'metadata',
    ]);
    expect(find.text('Draft saved'), findsOneWidget);
    await clearToast(tester);
  });

  testWidgets('Queue flow runs createBatch then queueBatch, in order', (
    WidgetTester tester,
  ) async {
    final _FakePickerRepository repo = _FakePickerRepository();
    await openSheet(
      tester,
      repo,
      mode: BatchCreateMode.queue,
      files: <String>['sub/x.png'],
    );

    expect(find.text('Queue batch'), findsOneWidget);
    // Queue mode waits for a profile: the confirm is inert until one is
    // picked (disabled state, not a spinner).
    await tester.ensureVisible(find.text('Queue batch'));
    await tester.pump();
    await tester.tap(find.text('Queue batch'), warnIfMissed: false);
    await tester.pumpAndSettle();
    expect(repo.calls, isEmpty);
    expect(
      find.text('Select a profile to queue this batch.'), // sheet hint
      findsOneWidget,
    );

    // Pick the only profile from the dropdown.
    await tester.tap(find.text('Choose a profile'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Raster presets'));
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.text('Queue batch'));
    await tester.pump();
    await tester.tap(find.text('Queue batch'));
    await tester.pumpAndSettle();

    expect(repo.calls, <String>['create', 'queue']); // order is the contract
    expect(repo.lastFiles, <String>['sub/x.png']);
    expect(repo.lastProfileId, 'pr-1');
    expect(repo.lastSteps?.map((BatchStep step) => step.key), <String>['ocr']);
    expect(find.text('Queued'), findsOneWidget);
    await clearToast(tester);
  });

  testWidgets('empty profile list shows the caption and Queue stays inert', (
    WidgetTester tester,
  ) async {
    final _FakePickerRepository repo = _FakePickerRepository()
      ..profiles = const <StepProfile>[];
    await openSheet(
      tester,
      repo,
      mode: BatchCreateMode.queue,
      files: <String>['a.jpg'],
    );

    expect(
      find.text('No step profiles yet — create one in Config, or save a draft'),
      findsOneWidget,
    );

    await tester.ensureVisible(find.text('Queue batch'));
    await tester.pump();
    await tester.tap(find.text('Queue batch'), warnIfMissed: false);
    await tester.pumpAndSettle();
    expect(repo.calls, isEmpty);
  });

  testWidgets('backend rejection surfaces its detail as an error toast', (
    WidgetTester tester,
  ) async {
    final _FakePickerRepository repo = _FakePickerRepository()
      ..createError = const ServerException(
        message: 'No valid steps for media type.',
      );
    await openSheet(
      tester,
      repo,
      mode: BatchCreateMode.draft,
      files: <String>['a.jpg'],
    );

    await tester.ensureVisible(find.text('Save draft'));
    await tester.pump();
    await tester.tap(find.text('Save draft'));
    await tester.pumpAndSettle();

    expect(find.text('No valid steps for media type.'), findsOneWidget);
    expect(find.text('Draft saved'), findsNothing);
    await clearToast(tester);
  });
}
