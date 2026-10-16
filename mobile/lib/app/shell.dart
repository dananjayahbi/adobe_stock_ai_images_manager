import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:lucide_flutter/lucide_flutter.dart';

import 'theme/tokens.dart';

/// Builds the app-wide scaffold owning the five branch navigators of the
/// [StatefulShellRoute] (05 §1.1). Wired by `router.dart`.
Widget buildShell(
  BuildContext context,
  GoRouterState state,
  StatefulNavigationShell shell,
) {
  return AppShell(shell: shell);
}

/// Shell body: the active branch navigator over a leather bottom nav with
/// the signature double-hairline top, brass sliding indicator and haptic
/// tab-change tick (04 §1.4, §8.4).
class AppShell extends StatelessWidget {
  const AppShell({super.key, required this.shell});

  /// The nested navigator container provided by GoRouter.
  final StatefulNavigationShell shell;

  void _onSelected(int index) {
    if (index != shell.currentIndex) {
      unawaited(HapticFeedback.lightImpact());
    }
    // Re-tapping the active tab pops it back to its root (GoRouter contract).
    shell.goBranch(index, initialLocation: index == shell.currentIndex);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: shell,
      bottomNavigationBar: ShellBottomNav(
        selectedIndex: shell.currentIndex,
        onSelected: _onSelected,
      ),
    );
  }
}

/// The five fixed tabs of the studio (05 §1.1) — `type: fixed`, no shifting.
class ShellBottomNav extends StatelessWidget {
  const ShellBottomNav({
    super.key,
    required this.selectedIndex,
    required this.onSelected,
  });

  /// Index of the highlighted tab.
  final int selectedIndex;

  /// Fires on every tap; the shell adds the haptic tick on change.
  final ValueChanged<int> onSelected;

  static const List<({IconData icon, String label})> tabs =
      <({IconData icon, String label})>[
    (icon: LucideIcons.house, label: 'HOME'),
    (icon: LucideIcons.layoutGrid, label: 'GALLERY'),
    (icon: LucideIcons.factory, label: 'PROCESS'),
    (icon: LucideIcons.send, label: 'DELIVERY'),
    (icon: LucideIcons.ellipsis, label: 'MORE'),
  ];

  static const double _kBarHeight = 60;
  static const double _kIndicatorWidth = 24;

  @override
  Widget build(BuildContext context) {
    final double bottomInset = MediaQuery.paddingOf(context).bottom;
    return Container(
      padding: EdgeInsets.only(bottom: bottomInset),
      color: AppColors.leather,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Signature double-hairline: 1 px parchment-400, 1 px gap, then
          // the inner rule at 40% (web `.frame-card` inset, 04 §1.4).
          Container(height: 1, color: AppColors.parchment400),
          const SizedBox(height: 1),
          Container(
            height: 1,
            color: AppColors.parchment400.withValues(alpha: 0.4),
          ),
          SizedBox(
            height: _kBarHeight,
            child: LayoutBuilder(
              builder: (BuildContext context, BoxConstraints constraints) {
                final double tabWidth =
                    constraints.maxWidth / tabs.length;
                final double indicatorLeft = tabWidth * selectedIndex +
                    (tabWidth - _kIndicatorWidth) / 2;
                return Stack(
                  children: [
                    Positioned.fill(
                      child: Row(
                        children: [
                          for (int i = 0; i < tabs.length; i++)
                            Expanded(
                              child: _Tab(
                                icon: tabs[i].icon,
                                label: tabs[i].label,
                                selected: i == selectedIndex,
                                onTap: () => onSelected(i),
                              ),
                            ),
                        ],
                      ),
                    ),
                    // Brass rule slides between tabs (~250 ms, easeOutCubic).
                    AnimatedPositioned(
                      duration: const Duration(milliseconds: 250),
                      curve: Curves.easeOutCubic,
                      left: indicatorLeft,
                      top: 0,
                      width: _kIndicatorWidth,
                      height: 2,
                      child: DecoratedBox(
                        decoration: BoxDecoration(
                          color: AppColors.brass400,
                          borderRadius: BorderRadius.circular(1),
                        ),
                      ),
                    ),
                  ],
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _Tab extends StatelessWidget {
  const _Tab({
    required this.icon,
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final Color color = selected ? AppColors.brass400 : AppColors.ink400;
    return Semantics(
      button: true,
      selected: selected,
      label: label.toLowerCase(),
      child: InkWell(
        onTap: onTap,
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              icon,
              size: 22,
              color: color,
              // Color-weight change stands in for the missing fill variant
              // (lucide ships a static font; weight axis is ignored gracefully).
              weight: selected ? 600 : 400,
            ),
            const SizedBox(height: 4),
            Text(
              label,
              style: TextStyle(
                fontSize: 11,
                height: 1.2,
                letterSpacing: 0.18 * 11,
                fontWeight: FontWeight.w600,
                color: color,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
