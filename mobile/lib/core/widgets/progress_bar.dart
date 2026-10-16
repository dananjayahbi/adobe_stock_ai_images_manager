import 'package:flutter/material.dart';

import '../../../app/theme/tokens.dart';

/// Brass fill on a parchment-200 track (04 §3) — the dashboard's running-job
/// progress (05 §2.4) and any other bounded task.
///
/// * [value] in 0..1 → determinate fill; semantics announce the percentage.
/// * [value] = null → indeterminate: a brass segment slides back and forth
///   (1400 ms easeInOut).
/// * Reduced motion (`MediaQuery.disableAnimations`) → static: the determinate
///   bar still renders its exact width; the indeterminate segment parks
///   centered instead of sliding.
class ProgressBar extends StatefulWidget {
  const ProgressBar({
    super.key,
    this.value,
    this.color,
    this.height = 6,
  });

  /// Completion fraction 0..1; `null` renders the indeterminate bar.
  final double? value;

  /// Fill color; defaults to `brass-400`.
  final Color? color;

  /// Bar thickness in logical pixels.
  final double height;

  @override
  State<ProgressBar> createState() => _ProgressBarState();
}

class _ProgressBarState extends State<ProgressBar>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  bool _reducedMotion = false;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1400),
    );
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _reducedMotion = MediaQuery.disableAnimationsOf(context);
    _syncAnimation();
  }

  @override
  void didUpdateWidget(ProgressBar oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.value != widget.value) {
      _syncAnimation();
    }
  }

  void _syncAnimation() {
    final bool indeterminate = widget.value == null;
    if (!indeterminate || _reducedMotion) {
      _controller.stop();
    } else if (!_controller.isAnimating) {
      _controller.repeat(reverse: true);
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final double? fraction = widget.value?.clamp(0.0, 1.0).toDouble();
    final Color fill = widget.color ?? AppColors.brass400;
    final BorderRadius radius = BorderRadius.all(
      Radius.circular(widget.height / 2),
    );

    return Semantics(
      value: fraction == null
          ? null
          : '${(fraction * 100).round()}%',
      child: LayoutBuilder(
        builder: (BuildContext context, BoxConstraints constraints) {
          final double width = constraints.maxWidth.isFinite
              ? constraints.maxWidth
              : 0.0;
          final Widget track = ColoredBox(
            color: AppColors.parchment200,
            child: SizedBox(height: widget.height),
          );

          return ClipRRect(
            borderRadius: radius,
            child: SizedBox(
              width: width,
              height: widget.height,
              child: Stack(
                children: <Widget>[
                  Positioned.fill(child: track),
                  if (fraction != null)
                    Positioned(
                      left: 0,
                      top: 0,
                      bottom: 0,
                      width: width * fraction,
                      child: ColoredBox(color: fill),
                    )
                  else
                    _slidingSegment(width: width, fill: fill),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  /// Indeterminate brass segment: animated slide, or a centered park when
  /// reduced motion is on.
  Widget _slidingSegment({required double width, required Color fill}) {
    final double segmentWidth = width * 0.35;
    if (_reducedMotion) {
      return Positioned(
        left: (width - segmentWidth) / 2,
        top: 0,
        bottom: 0,
        width: segmentWidth,
        child: ColoredBox(color: fill),
      );
    }
    return AnimatedBuilder(
      animation: _controller,
      builder: (BuildContext context, Widget? child) {
        final double t = Curves.easeInOut.transform(_controller.value);
        return Positioned(
          left: t * (width - segmentWidth),
          top: 0,
          bottom: 0,
          width: segmentWidth,
          child: child ?? const SizedBox.shrink(),
        );
      },
      child: ColoredBox(color: fill),
    );
  }
}
