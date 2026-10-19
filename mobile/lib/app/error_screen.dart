import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../app/theme/tokens.dart';
import '../core/widgets/ghost_button.dart';
import '../core/widgets/label_caps.dart';
import '../core/widgets/live_dot.dart';
import '../core/widgets/primary_button.dart';
import '../core/widgets/stamp_badge.dart';
import '../features/settings/data/health_api.dart';
import '../features/settings/data/profile_store.dart';
import '../features/settings/presentation/settings_controller.dart';

/// `/error?reason=offline|server` — last-resort full screen when bootstrap
/// can't reach any profile or a fatal client error lands (05 §2.11).
///
/// Contract screen (07 M5): a plain [StatelessWidget] with `reason`
/// defaulting to `offline`; the retry loop lives in the private stateful
/// body so the route-facing type stays exactly `ErrorScreen({this.reason})`.
class ErrorScreen extends StatelessWidget {
  const ErrorScreen({super.key, this.reason = 'offline'});

  /// `offline` (no signal) or `server` (out of order) — from `?reason=`.
  final String reason;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(child: _ErrorBody(reason: reason)),
    );
  }
}

class _ErrorBody extends ConsumerStatefulWidget {
  const _ErrorBody({required this.reason});

  final String reason;

  @override
  ConsumerState<_ErrorBody> createState() => _ErrorBodyState();
}

class _ErrorBodyState extends ConsumerState<_ErrorBody> {
  /// Retry backoff schedule (05 §2.11): waits before retries 2, 3 and 4.
  static const List<Duration> kBackoff = <Duration>[
    Duration(seconds: 2),
    Duration(seconds: 5),
    Duration(seconds: 10),
  ];

  int _attempts = 0;
  bool _busy = false;
  String? _lastError;
  Timer? _timer;

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  bool get _offline => widget.reason != 'server';

  /// Completes after [duration] via a cancellable [Timer] — dispose cancels
  /// it, so a test that tears down mid-backoff never leaves a pending timer.
  Future<void> _delay(Duration duration) {
    final Completer<void> gate = Completer<void>();
    _timer?.cancel();
    _timer = Timer(duration, () {
      if (!gate.isCompleted) {
        gate.complete();
      }
    });
    return gate.future;
  }

  /// `GET {active.baseUrl}/health` loop: immediate attempt, then 2/5/10 s
  /// backoff between retries (up to 4 attempts). First 200 → replace `/hub`;
  /// exhaustion re-enables the Retry button with the last failure reason.
  Future<void> _retry() async {
    if (_busy) {
      return;
    }
    setState(() {
      _busy = true;
      _lastError = null;
    });
    final Future<HealthProbeResult> Function(String) probe =
        ref.read(profileHealthProbeProvider);
    while (_attempts <= kBackoff.length) {
      setState(() => _attempts++);
      final HealthProbeResult result =
          await probe(ref.read(activeProfileProvider).baseUrl);
      if (!mounted) {
        return;
      }
      if (result.ok) {
        context.go('/hub');
        return;
      }
      setState(() => _lastError = result.error);
      if (_attempts > kBackoff.length) {
        break; // Backoff exhausted — stop; the button re-arms below.
      }
      await _delay(kBackoff[_attempts - 1]);
      if (!mounted) {
        return;
      }
    }
    setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    final TextTheme textTheme = Theme.of(context).textTheme;
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(AppSpacing.xl),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 480),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              StampBadge(
                label: _offline ? 'NO SIGNAL' : 'OUT OF ORDER',
                tone: StampTone.failure,
                rotation: -6,
              ),
              const SizedBox(height: AppSpacing.xl),
              Text(
                _offline ? 'No signal.' : 'Server trouble.',
                textAlign: TextAlign.center,
                style: textTheme.displaySmall
                    ?.copyWith(color: AppColors.ink800),
              ),
              const SizedBox(height: AppSpacing.md),
              Text(
                _offline
                    ? "Can't reach the studio server on this connection "
                        'profile. Check the network, then retry — or pick '
                        'a profile that answers.'
                    : 'The studio server answered with an error. Retry in a '
                        'moment, or switch to another connection profile.',
                textAlign: TextAlign.center,
                style: textTheme.bodyMedium?.copyWith(
                  color: AppColors.ink400,
                  height: 1.5,
                ),
              ),
              if (_lastError != null) ...<Widget>[
                const SizedBox(height: AppSpacing.md),
                Text(
                  _lastError!,
                  textAlign: TextAlign.center,
                  style:
                      textTheme.bodySmall?.copyWith(color: AppColors.rust400),
                ),
              ],
              const SizedBox(height: AppSpacing.lg),
              if (_attempts > 0)
                LiveDot(label: 'ATTEMPT $_attempts', enabled: _busy),
              const SizedBox(height: AppSpacing.xl),
              PrimaryButton(
                label: 'Retry connection',
                loading: _busy,
                expanded: true,
                onPressed: _busy ? null : _retry,
              ),
              const SizedBox(height: AppSpacing.sm),
              GhostButton(
                label: 'Choose another profile',
                expanded: true,
                onPressed: () => context.go('/more/connections'),
              ),
              const SizedBox(height: AppSpacing.lg),
              const LabelCaps(text: 'AI Stock Studio'),
            ],
          ),
        ),
      ),
    );
  }
}
