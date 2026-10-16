import 'package:ai_stock_studio/features/settings/data/health_api.dart';
import 'package:ai_stock_studio/features/settings/data/profile_auto_fallback.dart';
import 'package:ai_stock_studio/features/settings/data/profile_store.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late SharedPreferences prefs;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    prefs = await SharedPreferences.getInstance();
  });

  ProviderContainer createContainer(
    Future<HealthProbeResult> Function(String baseUrl) probe,
  ) {
    final ProviderContainer container = ProviderContainer(
      overrides: [
        sharedPreferencesProvider.overrideWithValue(prefs),
        profileFallbackProbeProvider.overrideWithValue(probe),
      ],
    );
    addTearDown(container.dispose);
    return container;
  }

  test('healthy active profile is left alone (single probe, no switch)',
      () async {
    final List<String> calls = <String>[];
    final ProviderContainer container = createContainer((String url) async {
      calls.add(url);
      return const HealthProbeResult.success(12);
    });

    final String? switched =
        await container.read(profileAutoFallbackProvider)();

    expect(switched, isNull);
    expect(calls, <String>['https://studio.hotelgo.lk']);
    expect(container.read(activeProfileProvider).id, 'tunnel');
    expect(prefs.getString(ProfileStore.activeKey), isNull);
  });

  test('dead active profile falls over to the first reachable candidate',
      () async {
    // Put a dead loopback profile in the active seat; the tunnel answers.
    final ProfileStore store = ProfileStore(prefs);
    await store.upsert(ProfileStore.localSeed);
    await store.setActive('local');

    final List<String> calls = <String>[];
    final ProviderContainer container = createContainer((String url) async {
      calls.add(url);
      if (url.contains('localhost')) {
        return const HealthProbeResult.failure('Host unreachable.');
      }
      return const HealthProbeResult.success(42);
    });

    final String? switched =
        await container.read(profileAutoFallbackProvider)();

    expect(switched, 'tunnel');
    expect(calls, <String>[
      'http://localhost:8007',
      'https://studio.hotelgo.lk',
    ]);
    expect(container.read(activeProfileProvider).id, 'tunnel');
    expect(container.read(activeProfileProvider).baseUrl,
        'https://studio.hotelgo.lk');
    expect(prefs.getString(ProfileStore.activeKey), 'tunnel');
  });

  test('every profile dead keeps the current one active', () async {
    final ProviderContainer container = createContainer(
      (String _) async => const HealthProbeResult.failure('Timed out.'),
    );

    final String? switched =
        await container.read(profileAutoFallbackProvider)();

    expect(switched, isNull);
    expect(container.read(activeProfileProvider).id, 'tunnel');
    expect(prefs.getString(ProfileStore.activeKey), isNull);
  });
}
