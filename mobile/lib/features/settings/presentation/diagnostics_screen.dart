import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_flutter/lucide_flutter.dart';

import '../../../app/theme/tokens.dart';
import '../../../core/widgets/app_card.dart';
import '../data/network_diagnostics.dart';

/// `/diagnostics` — on-device network ladder, one row per layer (system
/// resolver → DoH v4/v6 → UDP → full chain → relay → TLS → end-to-end
/// `/health`). Opens **pre-login** (the CONNECTION sheet links here) so a
/// failed sign-in is still diagnosable; every detail renders in full,
/// selectable text — screenshot-friendly by design.
class DiagnosticsScreen extends ConsumerStatefulWidget {
  const DiagnosticsScreen({super.key});

  @override
  ConsumerState<DiagnosticsScreen> createState() => _DiagnosticsScreenState();
}

class _DiagnosticsScreenState extends ConsumerState<DiagnosticsScreen> {
  List<DiagResult>? _results;
  bool _running = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _run());
  }

  Future<void> _run() async {
    if (_running) {
      return;
    }
    setState(() => _running = true);
    final List<DiagResult> results =
        await ref.read(diagnosticsProvider).runAll();
    if (!mounted) {
      return;
    }
    setState(() {
      _results = results;
      _running = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final TextTheme textTheme = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Network diagnostics')),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(AppSpacing.lg),
          children: <Widget>[
            Text(
              'One row per layer of the connection ladder — the first red '
              'row is where the app stops. Screenshot this screen when '
              'reporting a problem.',
              style: textTheme.bodySmall?.copyWith(
                color: AppColors.parchment400,
              ),
            ),
            const SizedBox(height: AppSpacing.md),
            _RunButton(running: _running, onPressed: _run),
            const SizedBox(height: AppSpacing.md),
            if (_results == null && _running)
              const Center(
                child: Padding(
                  padding: EdgeInsets.all(AppSpacing.lg),
                  child: CircularProgressIndicator(),
                ),
              ),
            if (_results != null)
              ..._results!.map((DiagResult r) => _ResultCard(result: r)),
            const SizedBox(height: AppSpacing.xl),
          ],
        ),
      ),
    );
  }
}

class _RunButton extends StatelessWidget {
  const _RunButton({required this.running, required this.onPressed});

  final bool running;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return OutlinedButton.icon(
      onPressed: running ? null : onPressed,
      icon: running
          ? const SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          : const Icon(LucideIcons.refreshCw, size: 16),
      label: Text(running ? 'Running…' : 'Run again'),
    );
  }
}

class _ResultCard extends StatelessWidget {
  const _ResultCard({required this.result});

  final DiagResult result;

  @override
  Widget build(BuildContext context) {
    final TextTheme textTheme = Theme.of(context).textTheme;
    final Color tone = result.ok ? AppColors.olive400 : AppColors.rust400;
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: AppCard(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Row(
            children: <Widget>[
              Icon(
                result.ok ? Icons.check_circle : Icons.error,
                size: 16,
                color: tone,
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Text(
                  result.name.toUpperCase(),
                  style: textTheme.labelSmall?.copyWith(
                    color: tone,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1.1,
                  ),
                ),
              ),
              Text(
                '${result.ms} ms',
                style: textTheme.labelSmall?.copyWith(
                  color: AppColors.parchment400,
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.xs),
          // Full, selectable, wrapping — deliberately unstyled for capture.
          SelectableText(
            result.detail,
            style: textTheme.bodySmall?.copyWith(
              color: AppColors.parchment400,
              height: 1.4,
            ),
          ),
        ],
        ),
      ),
    );
  }
}
