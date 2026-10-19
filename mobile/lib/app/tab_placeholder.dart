import 'package:flutter/material.dart';
import 'package:lucide_flutter/lucide_flutter.dart';

import '../core/widgets/label_caps.dart';
import 'theme/tokens.dart';

/// Generic tab body for workspaces a later milestone will replace (05 §1.1:
/// `/gallery`, `/process`, `/delivery`, `/more` land in M3–M5).
///
/// Keeps each shell branch navigable and labeled before its real screen
/// exists; swap the route target, not this widget, when the screen lands.
class TabPlaceholder extends StatelessWidget {
  const TabPlaceholder({
    super.key,
    required this.label,
    this.icon = LucideIcons.clock,
    this.message,
  });

  /// Tab name as shown in the bottom nav (`Gallery`, `Process`, …).
  final String label;

  /// Leading glyph matching the tab's Lucide icon where sensible.
  final IconData icon;

  /// Milestone note; defaults to a generic arrival line.
  final String? message;

  @override
  Widget build(BuildContext context) {
    final TextTheme textTheme = Theme.of(context).textTheme;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.xl),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(icon, size: 40, color: AppColors.parchment600),
                const SizedBox(height: AppSpacing.lg),
                Text(
                  label,
                  textAlign: TextAlign.center,
                  style: textTheme.displaySmall,
                ),
                const SizedBox(height: AppSpacing.md),
                LabelCaps(text: message ?? '$label arrives soon'),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
