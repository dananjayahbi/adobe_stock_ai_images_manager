import 'dart:convert';

import 'package:ai_stock_studio/features/settings/data/profile_store.dart';
import 'package:ai_stock_studio/features/settings/domain/connection_profile.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// One-time legacy purge: upgrades still carry the old first-run
/// `[local, tunnel]` seed (a localhost profile — the phone itself on a
/// device). The store drops it exactly once, reassigns the active profile,
/// and never touches profiles added afterwards.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  Future<SharedPreferences> prefsWith(
    Map<String, Object> values,
  ) async {
    SharedPreferences.setMockInitialValues(values);
    return SharedPreferences.getInstance();
  }

  String encode(List<ConnectionProfile> profiles) => jsonEncode(
        profiles.map((p) => p.toJson()).toList(growable: false),
      );

  group('legacy localhost purge (one-time)', () {
    test('drops the old local seed and keeps the tunnel', () async {
      final SharedPreferences prefs = await prefsWith(<String, Object>{
        ProfileStore.profilesKey: encode(<ConnectionProfile>[
          ProfileStore.localSeed,
          ProfileStore.tunnelSeed,
        ]),
        ProfileStore.activeKey: 'local',
      });
      final ProfileStore store = ProfileStore(prefs);

      final List<ConnectionProfile> result = store.profiles();
      expect(result.map((p) => p.id).toList(), <String>['tunnel']);
      // Active reassigned off the purged entry.
      expect(store.activeProfile().id, 'tunnel');
      expect(prefs.getString(ProfileStore.activeKey), 'tunnel');
      // Migration consumed.
      expect(prefs.getBool(ProfileStore.migratedLegacyLocalKey), isTrue);
      // And the purge is persisted for the next cold start.
      final String? persisted = prefs.getString(ProfileStore.profilesKey);
      expect(persisted, isNot(contains('localhost')));
    });

    test('purges loopback URLs regardless of profile id', () async {
      final SharedPreferences prefs = await prefsWith(<String, Object>{
        ProfileStore.profilesKey: encode(<ConnectionProfile>[
          const ConnectionProfile(
            id: 'old-quick',
            label: 'Quick tunnel',
            baseUrl: 'http://127.0.0.1:8007',
          ),
          ProfileStore.tunnelSeed,
        ]),
      });
      final ProfileStore store = ProfileStore(prefs);
      expect(store.profiles().map((p) => p.id).toList(), <String>['tunnel']);
    });

    test('keeps a manual LAN profile while purging the local one',
        () async {
      final SharedPreferences prefs = await prefsWith(<String, Object>{
        ProfileStore.profilesKey: encode(<ConnectionProfile>[
          ProfileStore.localSeed,
          ProfileStore.tunnelSeed,
          const ConnectionProfile(
            id: 'lan',
            label: 'Office',
            baseUrl: 'http://192.168.1.244:8007',
          ),
        ]),
      });
      final ProfileStore store = ProfileStore(prefs);
      expect(
        store.profiles().map((p) => p.id).toList(),
        <String>['tunnel', 'lan'],
      );
    });
  });

  group('flag semantics', () {
    test('after migration ran, later additions are never purged', () async {
      final SharedPreferences prefs = await prefsWith(<String, Object>{
        ProfileStore.migratedLegacyLocalKey: true,
        ProfileStore.profilesKey: encode(<ConnectionProfile>[
          ProfileStore.tunnelSeed,
          ProfileStore.localSeed, // dev re-add post-migration — allowed
        ]),
      });
      final ProfileStore store = ProfileStore(prefs);
      expect(
        store.profiles().map((p) => p.id).toList(),
        <String>['tunnel', 'local'],
      );
    });

    test('first-run heal consumes the flag; later upserts survive',
        () async {
      // The exact sequence every test fixture and the Connections → Add
      // flow uses: first read seeds, then a profile is written.
      final SharedPreferences prefs = await prefsWith(<String, Object>{});
      final ProfileStore store = ProfileStore(prefs);
      expect(store.profiles().map((p) => p.id).toList(), <String>['tunnel']);

      await store.upsert(ProfileStore.localSeed);
      await store.setActive('local');

      expect(store.profiles().map((p) => p.id).toList(),
          <String>['tunnel', 'local']);
      expect(store.activeProfile().id, 'local');
    });
  });
}
