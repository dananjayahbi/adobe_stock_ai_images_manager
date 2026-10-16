import 'dart:async';

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:lucide_flutter/lucide_flutter.dart';

import 'package:ai_stock_studio/app/theme/tokens.dart';

/// Tone variants for [showAppToast].
enum ToastTone { success, warning, error, neutral }

OverlayEntry? _activeToastEntry;
Timer? _activeToastTimer;

void _removeActiveToast() {
  _activeToastTimer?.cancel();
  _activeToastTimer = null;
  final OverlayEntry? entry = _activeToastEntry;
  _activeToastEntry = null;
  entry?.remove();
}

/// Inserts a transient [AppToast] above the bottom navigation.
///
/// Only one toast is shown at a time; a new call replaces the current one.
void showAppToast(
  BuildContext context,
  String message, {
  ToastTone tone = ToastTone.neutral,
  Duration duration = const Duration(seconds: 3),
}) {
  final OverlayState? overlay = Overlay.maybeOf(context, rootOverlay: true);
  if (overlay == null) {
    return;
  }
  _removeActiveToast();
  final OverlayEntry entry = OverlayEntry(
    builder: (BuildContext context) => AppToast(message: message, tone: tone),
  );
  _activeToastEntry = entry;
  _activeToastTimer = Timer(duration, _removeActiveToast);
  overlay.insert(entry);
}

/// Leather sheet with a brass left rule and stamp-font eyebrow (04 §2
/// ToastException). Positioned above the shell's bottom nav.
class AppToast extends StatefulWidget {
  const AppToast({
    super.key,
    required this.message,
    this.tone = ToastTone.neutral,
  });

  /// Toast body text.
  final String message;

  /// Icon + eyebrow variant.
  final ToastTone tone;

  @override
  State<AppToast> createState() => _AppToastState();
}

class _AppToastState extends State<AppToast>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  bool _started = false;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 400),
    );
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_started) {
      return;
    }
    _started = true;
    if (MediaQuery.disableAnimationsOf(context)) {
      _controller.value = 1.0;
    } else {
      _controller.forward();
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  IconData get _icon => switch (widget.tone) {
        ToastTone.success => LucideIcons.circleCheck,
        ToastTone.warning => LucideIcons.triangleAlert,
        ToastTone.error => LucideIcons.circleX,
        ToastTone.neutral => LucideIcons.info,
      };

  Color get _toneColor => switch (widget.tone) {
        ToastTone.success => AppColors.olive400,
        ToastTone.warning => AppColors.rust400,
        ToastTone.error => AppColors.rust400,
        ToastTone.neutral => AppColors.ink400,
      };

  String get _eyebrow => switch (widget.tone) {
        ToastTone.success => 'OK',
        ToastTone.warning => 'WARN',
        ToastTone.error => 'ERROR',
        ToastTone.neutral => 'NOTICE',
      };

  @override
  Widget build(BuildContext context) {
    // Shell bottom nav is 60 dp + the bottom safe-area inset.
    final double bottomInset =
        MediaQuery.paddingOf(context).bottom + 60 + AppSpacing.md;
    final TextTheme textTheme = Theme.of(context).textTheme;

    return IgnorePointer(
      child: AnimatedBuilder(
        animation: _controller,
        builder: (BuildContext context, Widget? child) {
          final double t = Curves.easeOutCubic.transform(_controller.value);
          return Opacity(
            opacity: t,
            child: Transform.translate(
              offset: Offset(0, (1 - t) * 12),
              child: child,
            ),
          );
        },
        child: Align(
          alignment: Alignment.bottomCenter,
          child: Padding(
            padding: EdgeInsets.fromLTRB(
              AppSpacing.xl,
              0,
              AppSpacing.xl,
              bottomInset,
            ),
            child: Semantics(
              liveRegion: true,
              child: Container(
                constraints: const BoxConstraints(maxWidth: 520),
                decoration: BoxDecoration(
                  color: AppColors.leather,
                  borderRadius: const BorderRadius.all(
                    Radius.circular(AppRadii.md),
                  ),
                  border: const Border(
                    left: BorderSide(color: AppColors.brass400, width: 3),
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withValues(alpha: 0.5),
                      offset: const Offset(0, 2),
                      blurRadius: 8,
                    ),
                  ],
                ),
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(
                    AppSpacing.md,
                    AppSpacing.sm,
                    AppSpacing.lg,
                    AppSpacing.sm,
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Icon(_icon, size: 20, color: _toneColor),
                      const SizedBox(width: AppSpacing.sm),
                      Flexible(
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              _eyebrow,
                              style: GoogleFonts.specialElite(
                                fontSize: 11,
                                height: 1.2,
                                letterSpacing: 1.5,
                                color: _toneColor,
                              ),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              widget.message,
                              style: textTheme.bodyMedium?.copyWith(
                                color: AppColors.ink800,
                                height: 1.4,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
