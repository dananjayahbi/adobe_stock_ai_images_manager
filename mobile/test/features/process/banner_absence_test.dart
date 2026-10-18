import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:ai_stock_studio/app/theme/theme.dart';
import 'package:ai_stock_studio/core/widgets/connection_profile_banner.dart';
import 'package:ai_stock_studio/features/process/domain/batch.dart';
import 'package:ai_stock_studio/features/process/domain/batch_step.dart';
import 'package:ai_stock_studio/features/process/domain/fs_repository.dart';
import 'package:ai_stock_studio/features/process/domain/process_repository.dart';
import 'package:ai_stock_studio/features/process/presentation/explorer/explorer_screen.dart';
import 'package:ai_stock_studio/features/process/presentation/new_batch_screen.dart';
import 'package:ai_stock_studio/features/settings/data/profile_store.dart';
import 'package:ai_stock_studio/features/settings/domain/connection_profile.dart';

/// Only `fetchProfiles` can be reached (the selection bar watches both
/// media types); everything else stays unreachable.
class _FakeProcessRepository implements ProcessRepository {
  @override
  Future<List<StepProfile>> fetchProfiles({String? mediaType}) async =>
      const <StepProfile>[];

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
  Future<void> deleteBatch(String batchId) async => throw UnimplementedError();

  @override
  Future<StepCatalog> fetchStepCatalog({String? mediaType}) async =>
      throw UnimplementedError();

  @override
  Future<Batch> createBatch({
    required String name,
    required String mediaType,
    required List<BatchStep> steps,
    String? profileId,
  }) async => throw UnimplementedError();

  @override
  Future<StepProfile> createProfile({
    required String name,
    required String mediaType,
    required List<BatchStep> steps,
  }) async => throw UnimplementedError();

  @override
  Future<Batch> cancelBatch(String batchId) async => throw UnimplementedError();
}

/// Configured source folder with an empty root listing — no thumbs, no IO.
class _FakeFsRepository implements FsRepository {
  @override
  Future<FsRoot> fetchRoot() async =>
      const FsRoot(configured: true, path: 'E:/source', exists: true);

  @override
  Future<FsListing> fetchListing(String path) async => FsListing(
    path: path,
    segments: const <String>[],
    parent: null,
    dirs: const <String>[],
    files: const <FsFile>[],
  );

  @override
  String thumbUrl(String path) => '/api/fs/thumb?path=$path';
}

/// Deterministic active profile (thumb base for the browser).
class _FakeActiveProfile extends ActiveProfileNotifier {
  @override
  ConnectionProfile build() => const ConnectionProfile(
    id: 'p-1',
    label: 'Test',
    baseUrl: 'https://studio.test',
  );
}

void main() {
  setUpAll(() {
    GoogleFonts.config.allowRuntimeFetching = false;
    SharedPreferences.setMockInitialValues({});
  });

  testWidgets('the New batch wizard carries no connection-profile banner', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      ProviderScope(
        child: MaterialApp(
          theme: buildAppTheme(),
          home: const NewBatchScreen(),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.text('New batch'), findsOneWidget); // screen rendered
    expect(find.byType(ConnectionProfileBanner), findsNothing);
  });

  testWidgets('the source picker carries no connection-profile banner', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          fsRepositoryProvider.overrideWithValue(_FakeFsRepository()),
          processRepositoryProvider.overrideWithValue(_FakeProcessRepository()),
          activeProfileProvider.overrideWith(_FakeActiveProfile.new),
        ],
        child: MaterialApp(
          theme: buildAppTheme(),
          home: const ExplorerScreen(),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.text('Select images'), findsOneWidget); // screen rendered
    expect(find.byType(ConnectionProfileBanner), findsNothing);
  });
}
