import 'dart:convert';

import 'package:ai_stock_studio/features/settings/data/profile_store.dart';
import 'package:ai_stock_studio/features/settings/domain/connection_profile.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late SharedPreferences prefs;
  late ProfileStore store;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    prefs = await SharedPreferences.getInstance();
    store = ProfileStore(prefs);
  });

  test('seeds profiles on first load and persists the JSON', () {
    final List<ConnectionProfile> profiles = store.profiles();
    expect(profiles, hasLength(1));

    // Tunnel-only first run — localhost is never seeded on mobile.
    final ConnectionProfile tunnel = profiles.first;
    expect(tunnel.id, 'tunnel');
    expect(tunnel.label, 'Tunnel');
    expect(tunnel.baseUrl, 'https://studio.hotelgo.lk');
    expect(tunnel.hint, contains('studio.hotelgo.lk'));

    final String? raw = prefs.getString(ProfileStore.profilesKey);
    expect(raw, isNotNull);
    final List<dynamic> decoded = jsonDecode(raw!) as List<dynamic>;
    expect(decoded, hasLength(1));
    expect(decoded.first['id'], 'tunnel');

    // Missing active id â†’ first (only) seed.
    expect(store.activeProfile().id, 'tunnel');
  });

  test('upsert and setActive persist JSON', () async {
    store.profiles();
    const ConnectionProfile custom = ConnectionProfile(
      id: 'hotspot',
      label: 'Hotspot',
      baseUrl: 'http://192.168.43.1:8007',
    );

    await store.upsert(custom);
    List<dynamic> decoded =
        jsonDecode(prefs.getString(ProfileStore.profilesKey)!) as List<dynamic>;
    expect(decoded, hasLength(2));
    expect(decoded.last['id'], 'hotspot');
    expect(store.profiles().last.label, 'Hotspot');

    // Upserting the same id replaces in place â€” no duplicates.
    await store.upsert(custom.copyWith(label: 'Phone hotspot'));
    decoded =
        jsonDecode(prefs.getString(ProfileStore.profilesKey)!) as List<dynamic>;
    expect(decoded, hasLength(2));
    expect(
      store.profiles().where((p) => p.id == 'hotspot'),
      hasLength(1),
    );
    expect(
      store.profiles().firstWhere((p) => p.id == 'hotspot').label,
      'Phone hotspot',
    );

    await store.setActive('hotspot');
    expect(prefs.getString(ProfileStore.activeKey), 'hotspot');
    expect(store.activeProfile().id, 'hotspot');
  });

  test('unknown or missing active id falls back to the first seed',
      () async {
    store.profiles();
    expect(store.activeProfile().id, 'tunnel');

    await store.setActive('does-not-exist');
    expect(store.activeProfile().id, 'tunnel');

    // A real, explicitly-added profile resolves normally.
    await store.upsert(ProfileStore.localSeed);
    await store.setActive('local');
    expect(store.activeProfile().id, 'local');
  });

  test('remove drops the profile and reassigns the active one', () async {
    store.profiles();
    await store.upsert(ProfileStore.localSeed);
    await store.setActive('local');

    await store.remove('local');
    expect(store.profiles().map((p) => p.id), <String>['tunnel']);
    expect(store.activeProfile().id, 'tunnel');

    // Emptying the list re-seeds the built-in tunnel.
    await store.remove('tunnel');
    expect(store.profiles().map((p) => p.id), <String>['tunnel']);
    expect(store.activeProfile().id, 'tunnel');
  });

  test('corrupt stored JSON heals back to the seeds', () async {
    await prefs.setString(ProfileStore.profilesKey, '{not json');
    expect(store.profiles().map((p) => p.id), <String>['tunnel']);
    expect(
      jsonDecode(prefs.getString(ProfileStore.profilesKey)!) as List<dynamic>,
      hasLength(1),
    );
  });

  test('providers resolve the active profile from SharedPreferences', () {
    store.profiles();
    final ProviderContainer container = ProviderContainer(
      overrides: [
        sharedPreferencesProvider.overrideWith((ref) => prefs),
      ],
    );
    addTearDown(container.dispose);

    expect(container.read(activeProfileProvider).id, 'tunnel');
    expect(container.read(profileStoreProvider).profiles(), hasLength(1));
    expect(
      container.read(activeProfileProvider).baseUrl,
      'https://studio.hotelgo.lk',
    );
  });
}
