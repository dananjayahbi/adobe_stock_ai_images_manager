import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ai_stock_studio/features/platforms/presentation/platforms_controller.dart';

void main() {
  late ProviderContainer container;

  setUp(() {
    container = ProviderContainer();
    addTearDown(container.dispose);
  });

  test('initial active platform id is adobe_stock', () {
    expect(container.read(activePlatformIdProvider), 'adobe_stock');
  });

  test('select() switches the active platform', () {
    container.read(activePlatformIdProvider.notifier).select('freepik');
    expect(container.read(activePlatformIdProvider), 'freepik');

    container.read(activePlatformIdProvider.notifier).select('wirestock');
    expect(container.read(activePlatformIdProvider), 'wirestock');
  });

  test('selecting the current id is a no-op (no state churn)', () {
    final ActivePlatformNotifier notifier =
        container.read(activePlatformIdProvider.notifier);
    int rebuilds = 0;
    container.listen(activePlatformIdProvider, (_, _) => rebuilds++);

    notifier.select('adobe_stock'); // already the default — no change
    expect(rebuilds, 0);

    notifier.select('freepik');
    expect(rebuilds, 1);

    notifier.select('freepik'); // same id again — still a no-op
    expect(rebuilds, 1);
    expect(container.read(activePlatformIdProvider), 'freepik');
  });
}
