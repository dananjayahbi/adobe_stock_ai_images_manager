import 'dart:math' as math;
import 'dart:ui' show lerpDouble;

import 'package:flutter/material.dart';

/// One-shot "stamp-in" entrance (04 §3): scale 1.15→1, rotate -6°→-2° and
/// opacity 0→1 over ~350 ms on a springy easeOutBack curve.
///
/// Ends at the signature -2° tilt. Honors
/// [MediaQuery.disableAnimations] by snapping straight to the final state.
class StampIn extends StatefulWidget {
  const StampIn({super.key, required this.child, this.delay = Duration.zero});

  /// Content stamped into place.
  final Widget child;

  /// Optional hold-off before the stamp fires.
  final Duration delay;

  @override
  State<StampIn> createState() => _StampInState();
}

class _StampInState extends State<StampIn> with SingleTickerProviderStateMixin {
  static const Duration _kDuration = Duration(milliseconds: 350);

  late final AnimationController _controller;
  late final CurvedAnimation _animation;
  bool _started = false;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(vsync: this, duration: widget.delay + _kDuration);
    final double total = _controller.duration!.inMilliseconds.toDouble();
    final double delayMs = widget.delay.inMilliseconds.toDouble();
    _animation = CurvedAnimation(
      parent: _controller,
      curve: Interval(delayMs / total, 1.0, curve: Curves.easeOutBack),
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

  @override
  Widget build(BuildContext context) {
    final bool instant = MediaQuery.disableAnimationsOf(context);
    return AnimatedBuilder(
      animation: _animation,
      builder: (BuildContext context, Widget? child) {
        final double t = instant ? 1.0 : _animation.value;
        // easeOutBack overshoots above 1 near the end; clamp only opacity.
        final double scale = lerpDouble(1.15, 1.0, t) ?? 1.0;
        final double angle = lerpDouble(-6, -2, t) ?? -2.0;
        return Opacity(
          opacity: t > 1.0 ? 1.0 : t,
          child: Transform.rotate(
            angle: angle * math.pi / 180,
            child: Transform.scale(scale: scale, child: child),
          ),
        );
      },
      child: widget.child,
    );
  }
}
