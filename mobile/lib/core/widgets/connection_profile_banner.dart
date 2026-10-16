import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_flutter/lucide_flutter.dart';

import 'package:ai_stock_studio/app/theme/tokens.dart';
import 'package:ai_stock_studio/features/settings/data/health_api.dart';
import 'package:ai_stock_studio/features/settings/data/profile_store.dart';
import 'package:ai_stock_studio/features/settings/domain/connection_profile.dart';

/// Slim strip reporting the active connection profile's transport plus a
/// health dot (04 §2, M5): brass-tinted `TUNNEL · <host>` for HTTPS origins,
/// `LOCAL` for loopback — and an olive `ONLINE` / rust `OFFLINE` dot once a
/// probe has an answer.
///
/// Probing is deliberately cheap: a single debounced `GET /health` runs when
/// the active profile **changes** (switch/activate) — no polling, no request
/// on first mount (the persisted `lastStatus` seeds the dot instead), so
/// screens stay test- and battery-friendly.
class ConnectionProfileBanner extends ConsumerStatefulWidget {
  const ConnectionProfileBanner({super.key});

  /// Debounce so a burst of profile edits fires one probe, not many.
  static const Duration probeDebounce = Duration(milliseconds: 300);

  @override
  ConsumerState<ConnectionProfileBanner> createState() =>
      _ConnectionProfileBannerState();
}

class _ConnectionProfileBannerState
    extends ConsumerState<ConnectionProfileBanner> {
  Timer? _debounce;
  int _generation = 0;

  /// `null` = no verdict yet (dot hidden), true/false = ONLINE/OFFLINE.
  bool? _online;

  @override
  void initState() {
    super.initState();
    // Seed from the persisted verdict — mount itself never touches Dio.
    final String? status = ref.read(activeProfileProvider).lastStatus;
    _online = switch (status) {
      'ok' => true,
      'unreachable' => false,
      _ => null,
    };
  }

  @override
  void dispose() {
    _debounce?.cancel();
    super.dispose();
  }

  void _onProfileChanged() {
    _debounce?.cancel();
    _debounce = Timer(
      ConnectionProfileBanner.probeDebounce,
      _probe,
    );
  }

  Future<void> _probe() async {
    final int generation = ++_generation;
    final bool ok = await ref.read(healthApiProvider).ping();
    if (!mounted || generation != _generation) {
      return; // Profile changed again while this probe was in flight.
    }
    setState(() => _online = ok);
  }

  String _hostOf(String baseUrl) {
    final String? host = Uri.tryParse(baseUrl)?.host;
    if (host == null || host.isEmpty) {
      return baseUrl;
    }
    return host;
  }

  @override
  Widget build(BuildContext context) {
    // Fires only on change (never on this initial subscription) — see class
    // doc: cheap, debounced, no polling.
    ref.listen(
      activeProfileProvider,
      (ConnectionProfile? previous, ConnectionProfile next) {
        if (previous != next) {
          _onProfileChanged();
        }
      },
    );
    final profile = ref.watch(activeProfileProvider);
    final String baseUrl = profile.baseUrl;

    final String label;
    final IconData icon;
    if (baseUrl.startsWith('https://') ||
        baseUrl.contains('trycloudflare.com')) {
      // Any HTTPS origin is the tunnel on this stack (LAN/local are http).
      label = 'TUNNEL · ${_hostOf(baseUrl)}';
      icon = LucideIcons.cloud;
    } else if (baseUrl.contains('localhost') ||
        baseUrl.contains('127.0.0.1')) {
      label = 'LOCAL';
      icon = LucideIcons.monitor;
    } else {
      return const SizedBox.shrink();
    }

    final TextStyle style =
        (Theme.of(context).textTheme.labelSmall ?? const TextStyle())
            .copyWith(
              color: AppColors.brass400,
              fontSize: 11,
              height: 1.2,
              letterSpacing: 0.18 * 11,
              fontWeight: FontWeight.w600,
            );

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.lg,
        vertical: AppSpacing.xs,
      ),
      decoration: const BoxDecoration(
        color: Color(0x1ACBA857), // brass-400 @ 10%
        border: Border(bottom: BorderSide(color: AppColors.parchment400)),
      ),
      child: Row(
        children: [
          Icon(icon, size: 14, color: AppColors.brass400),
          const SizedBox(width: AppSpacing.xs),
          // Flexible + ellipsis: the tunnel host ('studio.hotelgo.lk') is
          // much longer than 'LOCAL' and used to overflow the strip.
          Expanded(
            child: Text(
              label,
              style: style,
              overflow: TextOverflow.ellipsis,
              maxLines: 1,
            ),
          ),
          if (_online case final bool online) _HealthDot(online: online),
        ],
      ),
    );
  }
}

/// Olive `ONLINE` / rust `OFFLINE` dot + caption — text always carries the
/// state too, never color alone (04 §4).
class _HealthDot extends StatelessWidget {
  const _HealthDot({required this.online});

  final bool online;

  @override
  Widget build(BuildContext context) {
    final Color color = online ? AppColors.olive400 : AppColors.rust400;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        DecoratedBox(
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          child: const SizedBox(width: 7, height: 7),
        ),
        const SizedBox(width: AppSpacing.xs),
        Text(
          online ? 'ONLINE' : 'OFFLINE',
          style: Theme.of(context).textTheme.labelSmall?.copyWith(
                color: color,
                fontSize: 11,
                height: 1.2,
                letterSpacing: 0.18 * 11,
                fontWeight: FontWeight.w600,
              ),
        ),
      ],
    );
  }
}
