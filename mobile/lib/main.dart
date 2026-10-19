import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app/app.dart';
import 'app/bootstrap.dart';
import 'core/network/dio_factory.dart';
import 'features/auth/presentation/auth_controller.dart';
import 'features/settings/data/profile_store.dart';

Future<void> main() async {
  final BootstrapHandles handles = await bootstrap();
  runApp(
    ProviderScope(
      overrides: [
        sharedPreferencesProvider.overrideWithValue(handles.prefs),
        unauthorizedHandlerProvider.overrideWith(
          (ref) => () => ref.read(authControllerProvider.notifier).forceLogout(),
        ),
      ],
      child: const App(),
    ),
  );
}
