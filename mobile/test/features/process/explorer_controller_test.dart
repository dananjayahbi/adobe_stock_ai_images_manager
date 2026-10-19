import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:ai_stock_studio/core/utils/app_exception.dart';
import 'package:ai_stock_studio/features/process/domain/fs_repository.dart';
import 'package:ai_stock_studio/features/process/presentation/explorer/explorer_controller.dart';
import 'package:ai_stock_studio/features/settings/data/profile_store.dart';
import 'package:ai_stock_studio/features/settings/domain/connection_profile.dart';

/// Scriptable FS backend: per-path listings, per-path failures, root flag.
class _FakeFsRepository implements FsRepository {
  FsRoot root = const FsRoot(configured: true, path: 'E:/source', exists: true);
  Object? rootError;

  final Map<String, FsListing> listings = <String, FsListing>{};
  final Map<String, Object> listErrors = <String, Object>{};

  int rootCalls = 0;
  final List<String> listCalls = <String>[];

  @override
  Future<FsRoot> fetchRoot() async {
    rootCalls += 1;
    final Object? error = rootError;
    if (error != null) {
      throw error; // ignore: only_throw_errors — fake failure injection
    }
    return root;
  }

  @override
  Future<FsListing> fetchListing(String path) async {
    listCalls.add(path);
    final Object? error = listErrors[path];
    if (error != null) {
      throw error; // ignore: only_throw_errors — fake failure injection
    }
    return listings[path] ??
        FsListing(
          path: path,
          segments: const <String>[],
          parent: null,
          dirs: const <String>[],
          files: const <FsFile>[],
        );
  }

  @override
  String thumbUrl(String path) => '/api/fs/thumb?path=$path';
}

/// Deterministic active connection profile (thumb base for the browser).
class _FakeActiveProfile extends ActiveProfileNotifier {
  @override
  ConnectionProfile build() => const ConnectionProfile(
    id: 'p-1',
    label: 'Test',
    baseUrl: 'https://studio.test',
  );
}

FsListing _listing(
  String path, {
  List<String> segments = const <String>[],
  String? parent,
  List<String> dirs = const <String>[],
  List<FsFile> files = const <FsFile>[],
}) => FsListing(
  path: path,
  segments: segments,
  parent: parent,
  dirs: dirs,
  files: files,
);

void main() {
  late _FakeFsRepository fake;
  late ProviderContainer container;
  ProviderSubscription<AsyncValue<ExplorerState>>? pin;

  setUp(() {
    fake = _FakeFsRepository();
    container = ProviderContainer(
      overrides: [
        fsRepositoryProvider.overrideWithValue(fake),
        activeProfileProvider.overrideWith(() => _FakeActiveProfile()),
      ],
    );
    pin = null;
    addTearDown(container.dispose);
  });

  /// Pins the autoDispose provider **after** the test configured [fake] —
  /// an earlier pin in setUp would start the build before the fixtures
  /// exist (the build's awaits resume on the microtask queue between setUp
  /// and the test body).
  Future<ExplorerState> load() {
    pin ??= container.listen(explorerControllerProvider, (_, _) {});
    return container.read(explorerControllerProvider.future);
  }

  ExplorerController notifier() =>
      container.read(explorerControllerProvider.notifier);

  test('root load composes state: paths, listing rows, thumb base', () async {
    fake.listings[''] = _listing(
      '',
      dirs: const <String>['sub'],
      files: const <FsFile>[FsFile(name: 'a.jpg', size: 123)],
    );

    final ExplorerState state = await load();

    expect(fake.rootCalls, 1);
    expect(fake.listCalls, <String>['']);
    expect(state.path, '');
    expect(state.segments, isEmpty);
    expect(state.parent, isNull);
    expect(state.dirs, <String>['sub']);
    expect(state.files.single.name, 'a.jpg');
    expect(state.files.single.size, 123);
    expect(state.selected, isEmpty);
    expect(state.loading, isFalse);
    expect(state.thumbBase, 'https://studio.test');
  });

  test(
    'navigate composes rel paths and the selection survives folder hops',
    () async {
      fake.listings[''] = _listing(
        '',
        dirs: const <String>['sub'],
        files: const <FsFile>[FsFile(name: 'a.jpg')],
      );
      fake.listings['sub'] = _listing(
        'sub',
        segments: const <String>['sub'],
        parent: '',
        files: const <FsFile>[FsFile(name: 'b.jpg')],
      );
      await load();

      // Root file → bare name; toggling twice clears it.
      notifier().toggle('a.jpg');
      expect(
        container.read(explorerControllerProvider).value?.selected,
        <String>{'a.jpg'},
      );
      notifier().toggle('a.jpg');
      expect(
        container.read(explorerControllerProvider).value?.selected,
        isEmpty,
      );
      notifier().toggle('a.jpg');

      await notifier().navigate('sub');
      final ExplorerState sub = container
          .read(explorerControllerProvider)
          .value!;
      expect(fake.listCalls, <String>['', 'sub']);
      expect(sub.path, 'sub');
      expect(sub.segments, <String>['sub']);
      expect(sub.parent, '');
      expect(sub.relPath('b.jpg'), 'sub/b.jpg'); // child rule

      // Child file joins under the folder; selection keeps both rel paths.
      notifier().toggle('b.jpg');
      expect(
        container.read(explorerControllerProvider).value?.selected,
        <String>{'a.jpg', 'sub/b.jpg'},
      );

      // Back at the root, the child selection is retained; clear wipes it.
      await notifier().navigate('');
      expect(
        container.read(explorerControllerProvider).value?.selected,
        <String>{'a.jpg', 'sub/b.jpg'},
      );
      notifier().clearSelection();
      expect(
        container.read(explorerControllerProvider).value?.selected,
        isEmpty,
      );
    },
  );

  test('root configured=false surfaces UnconfiguredSourceException', () async {
    fake.root = const FsRoot(configured: false, path: null, exists: false);

    await expectLater(
      container.read(explorerControllerProvider.future),
      throwsA(isA<UnconfiguredSourceException>()),
    );
    expect(fake.listCalls, isEmpty); // no listing call without a folder
  });

  test('listing 400 (ValidationException) also maps to unconfigured', () async {
    fake.listErrors[''] = const ValidationException(
      message: 'Source folder is not configured.',
    );

    await expectLater(
      container.read(explorerControllerProvider.future),
      throwsA(isA<UnconfiguredSourceException>()),
    );
  });

  test('navigate failure becomes the error state; retry recovers with the '
      'selection intact', () async {
    fake.listings[''] = _listing(
      '',
      dirs: const <String>['sub'],
      files: const <FsFile>[FsFile(name: 'a.jpg')],
    );
    fake.listings['sub'] = _listing(
      'sub',
      segments: const <String>['sub'],
      parent: '',
    );
    await load();
    notifier().toggle('a.jpg');

    fake.listErrors['sub'] = const NetworkException(message: 'link down');
    await notifier().navigate('sub');

    final AsyncValue<ExplorerState> failed = container.read(
      explorerControllerProvider,
    );
    expect(failed.hasError, isTrue);
    expect(failed.error, isA<NetworkException>());

    // Manual retry (ErrorView button) re-runs the same path and restores
    // the selection kept in the controller.
    fake.listErrors.remove('sub');
    notifier().retry();
    final ExplorerState recovered = await load();
    expect(recovered.path, 'sub');
    expect(recovered.selected, <String>{'a.jpg'});
    expect(fake.listCalls, <String>['', 'sub', 'sub']);
  });
}
