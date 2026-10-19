import 'dart:io';

import 'package:ai_stock_studio/core/network/auth_cookie_jar.dart';
import 'package:ai_stock_studio/features/settings/data/health_api.dart';
import 'package:ai_stock_studio/features/settings/data/profile_store.dart';
import 'package:ai_stock_studio/features/settings/domain/settings_repository.dart';
import 'package:ai_stock_studio/features/settings/presentation/settings_controller.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:mocktail/mocktail.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _MockSecureStorage extends Mock implements FlutterSecureStorage {}

/// In-memory settings API for the save/test/reset coverage.
class _FakeSettingsRepository implements SettingsRepository {
  AppSettings settings = const AppSettings(
    llmBaseUrl: 'http://localhost:4006/api/gateway/v1',
    llmModel: 'test-model',
    llmApiKeyMasked: '********abcd',
    llmApiKeySet: true,
    llmContextWindow: 32768,
    braveSearchEnabled: false,
    braveSearchApiKeyMasked: '',
    braveSearchApiKeySet: false,
    effectiveBaseUrl: 'http://localhost:4006/api/gateway/v1',
    effectiveModel: 'test-model',
    effectiveUsesBrave: false,
  );

  final List<Map<String, dynamic>> updates = <Map<String, dynamic>>[];
  int testCalls = 0;
  int resetCalls = 0;

  @override
  Future<AppSettings> fetch() async => settings;

  @override
  Future<AppSettings> update(Map<String, dynamic> patch) async {
    updates.add(patch);
    settings = AppSettings.fromJson(<String, dynamic>{
      ...settings.toJson(),
      ...patch,
    });
    return settings;
  }

  @override
  Future<SettingsTestResult> test([Map<String, dynamic>? candidate]) async {
    testCalls++;
    return const SettingsTestResult(ok: true, model: 'test-model');
  }

  @override
  Future<AppSettings> reset() async {
    resetCalls++;
    return settings;
  }

  @override
  Future<String?> fetchUsername() async => 'admin';
}

extension on AppSettings {
  Map<String, dynamic> toJson() => <String, dynamic>{
        'llm_base_url': llmBaseUrl,
        'llm_model': llmModel,
        'llm_api_key_masked': llmApiKeyMasked,
        'llm_api_key_set': llmApiKeySet,
        'llm_context_window': llmContextWindow,
        'brave_search_enabled': braveSearchEnabled,
        'brave_search_api_key_masked': braveSearchApiKeyMasked,
        'brave_search_api_key_set': braveSearchApiKeySet,
        'effective_base_url': effectiveBaseUrl,
        'effective_model': effectiveModel,
        'effective_uses_brave': effectiveUsesBrave,
      };
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() {
    GoogleFonts.config.allowRuntimeFetching = false;
    // In-memory Keychain/Keystore for the switch flow's jar reads.
    FlutterSecureStorage.setMockInitialValues(<String, String>{});
  });

  late SharedPreferences prefs;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    prefs = await SharedPreferences.getInstance();
    // Two-profile fixture (tunnel-only seed + an inactive local, local
    // active) so the switch/delete semantics keep their original shape.
    final ProfileStore fixture = ProfileStore(prefs);
    await fixture.upsert(ProfileStore.localSeed);
    await fixture.setActive('local');
  });

  ProviderContainer createContainer({
    List<Override> extra = const <Override>[],
    Future<HealthProbeResult> Function(String baseUrl)? probe,
  }) {
    final ProviderContainer container = ProviderContainer(
      overrides: <Override>[
        sharedPreferencesProvider.overrideWithValue(prefs),
        if (probe != null) profileHealthProbeProvider.overrideWithValue(probe),
        ...extra,
      ],
    );
    addTearDown(container.dispose);
    return container;
  }

  group('profileSwitchHandlerProvider.switchTo', () {
    test('health success: state changes, sentinel provider invalidates',
        () async {
      int sentinelBuilds = 0;
      final Provider<int> sentinel = Provider<int>((Ref ref) {
        sentinelBuilds++;
        return sentinelBuilds;
      });
      final ProviderContainer container = createContainer(
        probe: (String baseUrl) async =>
            const HealthProbeResult.success(42),
        extra: <Override>[
          profileSwitchTargetsProvider
              .overrideWith((Ref ref) => <Provider<int>>[sentinel]),
        ],
      );
      container.listen<int>(sentinel, (_, _) {});
      expect(container.read(sentinel), 1);
      expect(container.read(activeProfileProvider).id, 'local');
      expect(
        container.read(profileSwitchTargetsProvider),
        contains(sentinel),
      );

      final SwitchOutcome outcome = await container
          .read(profileSwitchHandlerProvider)
          .switchTo('tunnel');

      expect(outcome.ok, isTrue);
      expect(outcome.latencyMs, 42);
      // Notifier-based provider republished — every watcher sees the flip.
      expect(container.read(activeProfileProvider).id, 'tunnel');
      expect(
        container.read(activeProfileProvider).baseUrl,
        'https://studio.hotelgo.lk',
      );
      // The seam's invalidation hit the sentinel (flush + rebuild).
      await container.pump();
      expect(sentinelBuilds, 2);
      expect(container.read(sentinel), 2);
      expect(prefs.getString(ProfileStore.activeKey), 'tunnel');
    });

    test('health failure: state unchanged, sentinel not invalidated',
        () async {
      int sentinelBuilds = 0;
      final Provider<int> sentinel = Provider<int>((Ref ref) {
        sentinelBuilds++;
        return sentinelBuilds;
      });
      final ProviderContainer container = createContainer(
        probe: (String baseUrl) async => const HealthProbeResult.failure(
          'Timed out after 3 s.',
        ),
        extra: <Override>[
          profileSwitchTargetsProvider
              .overrideWith((Ref ref) => <Provider<int>>[sentinel]),
        ],
      );
      container.listen<int>(sentinel, (_, _) {});
      expect(container.read(sentinel), 1);

      final SwitchOutcome outcome = await container
          .read(profileSwitchHandlerProvider)
          .switchTo('tunnel');

      expect(outcome.ok, isFalse);
      expect(outcome.error, 'Timed out after 3 s.');
      // Previous profile stays active — nothing else persisted, rebuilt.
      expect(container.read(activeProfileProvider).id, 'local');
      await container.pump();
      expect(sentinelBuilds, 1);
      expect(prefs.getString(ProfileStore.activeKey), 'local');
    });

    test('already-active profile is a no-op success without probing',
        () async {
      int probeCalls = 0;
      final ProviderContainer container = createContainer(
        probe: (String baseUrl) async {
          probeCalls++;
          return const HealthProbeResult.success(1);
        },
      );

      final SwitchOutcome outcome = await container
          .read(profileSwitchHandlerProvider)
          .switchTo('local');

      expect(outcome.ok, isTrue);
      expect(probeCalls, 0);
      expect(container.read(activeProfileProvider).id, 'local');
    });

    test('unknown profile id fails without touching state', () async {
      final ProviderContainer container = createContainer(
        probe: (String baseUrl) async =>
            const HealthProbeResult.success(1),
      );

      final SwitchOutcome outcome = await container
          .read(profileSwitchHandlerProvider)
          .switchTo('does-not-exist');

      expect(outcome.ok, isFalse);
      expect(outcome.error, 'Profile not found.');
      expect(container.read(activeProfileProvider).id, 'local');
    });
  });

  group('ProfileSwitchHandler.deleteProfile guard', () {
    test('blocks the active profile and keeps every list non-empty',
        () async {
      final ProviderContainer container = createContainer();

      final String? blocked = await container
          .read(profileSwitchHandlerProvider)
          .deleteProfile('local');

      expect(blocked, contains('active profile'));
      expect(
        container.read(profileStoreProvider).profiles().map((p) => p.id),
        containsAll(<String>['local', 'tunnel']),
      );

      // A non-active profile removes cleanly; the active one remains,
      // so the list can never empty through this path either.
      final String? ok = await container
          .read(profileSwitchHandlerProvider)
          .deleteProfile('tunnel');
      expect(ok, isNull);
      expect(
        container.read(profileStoreProvider).profiles().map((p) => p.id),
        <String>['local'],
      );
    });
  });

  group('SettingsController', () {
    test('save applies the patch and lands it in state', () async {
      final _FakeSettingsRepository repo = _FakeSettingsRepository();
      final ProviderContainer container = createContainer(
        extra: <Override>[
          settingsRepositoryProvider.overrideWithValue(repo),
        ],
      );

      await container.read(settingsControllerProvider.future);
      await container.read(settingsControllerProvider.notifier).save(
        <String, dynamic>{'llm_model': 'new-model'},
      );

      expect(repo.updates, hasLength(1));
      final AsyncValue<AppSettings> state =
          container.read(settingsControllerProvider);
      expect(state.value?.llmModel, 'new-model');
    });

    test('testCandidate and reset route to the repository', () async {
      final _FakeSettingsRepository repo = _FakeSettingsRepository();
      final ProviderContainer container = createContainer(
        extra: <Override>[
          settingsRepositoryProvider.overrideWithValue(repo),
        ],
      );
      await container.read(settingsControllerProvider.future);

      final SettingsTestResult result = await container
          .read(settingsControllerProvider.notifier)
          .testCandidate(<String, dynamic>{'llm_model': 'probe-me'});
      expect(result.ok, isTrue);
      expect(repo.testCalls, 1);

      await container
          .read(settingsControllerProvider.notifier)
          .reset();
      expect(repo.resetCalls, 1);
    });

    test('forceReducedMotionProvider toggles from its notifier', () {
      final ProviderContainer container = createContainer();
      expect(container.read(forceReducedMotionProvider), isFalse);

      container.read(forceReducedMotionProvider.notifier).set(true);
      expect(container.read(forceReducedMotionProvider), isTrue);

      container.read(forceReducedMotionProvider.notifier).set(false);
      expect(container.read(forceReducedMotionProvider), isFalse);
    });
  });

  group('per-profile cookie isolation (06 §4.5)', () {
    late _MockSecureStorage storage;
    late Map<String, String?> values;

    setUp(() {
      storage = _MockSecureStorage();
      values = <String, String?>{};
      when(() => storage.write(
            key: any(named: 'key'),
            value: any(named: 'value'),
          )).thenAnswer((invocation) async {
        values[invocation.namedArguments[#key]! as String] =
            invocation.namedArguments[#value] as String?;
      });
      when(() => storage.read(key: any(named: 'key')))
          .thenAnswer((invocation) async =>
              values[invocation.namedArguments[#key]! as String]);
      when(() => storage.delete(key: any(named: 'key')))
          .thenAnswer((invocation) async {
        values.remove(invocation.namedArguments[#key]! as String);
      });
    });

    test('a 401-style clear on profile B never removes profile A\'s cookie',
        () async {
      String activeId = 'local';
      final AuthCookieJar jar = AuthCookieJar(
        storage: storage,
        profileId: () => activeId,
      );

      // Login on profile A stores its session pair under A's key.
      await jar.saveFromResponse(
        Uri.parse('http://localhost:8007/api/auth/login'),
        <Cookie>[Cookie('studio_session', 'token-a')],
      );
      expect(values[AuthCookieJar.keyFor('local')],
          'studio_session=token-a');

      // Switch to profile B; a 401 forces the jar teardown for B only.
      activeId = 'tunnel';
      await jar.saveFromResponse(
        Uri.parse('https://studio.example.com/api/auth/login'),
        <Cookie>[Cookie('studio_session', 'token-b')],
      );
      await jar.clear(); // auth forceLogout on B's 401.

      // B's key is gone; A's stored session survives untouched.
      expect(values.containsKey(AuthCookieJar.keyFor('tunnel')), isFalse);
      expect(values[AuthCookieJar.keyFor('local')],
          'studio_session=token-a');

      // Switching back to A replays A's cookie with zero re-auth.
      activeId = 'local';
      final List<Cookie> replayed =
          await jar.loadForRequest(Uri.parse('http://localhost:8007/x'));
      expect(replayed, hasLength(1));
      expect(replayed.single.value, 'token-a');
    });
  });
}
