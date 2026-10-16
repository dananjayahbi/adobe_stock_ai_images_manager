import 'package:flutter/material.dart';

import '../../../app/theme/tokens.dart';
import 'label_caps.dart';

/// Pulsing 8 dp brass dot with a label-caps tail — the dashboard's "a batch
/// is alive right now" signal (05 §2.4 running-job card, 04 §4 live region).
///
/// Pulses opacity + scale on a 1200 ms ease loop. Reduced motion
/// (`MediaQuery.disableAnimations`) freezes the dot at its mid pose, and
/// [enabled] = false keeps it static without changing layout.
class LiveDot extends StatefulWidget {
  const LiveDot({super.key, this.label = 'LIVE', this.enabled = true});

  /// Label-caps text beside the dot (e.g. 'RUNNING').
  final String label;

  /// False → static dot (job just finished, decorative use, tests).
  final bool enabled;

  @override
  State<LiveDot> createState() => _LiveDotState();
}

class _LiveDotState extends State<LiveDot> with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _opacity;
  late final Animation<double> _scale;
  bool _reducedMotion = false;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    );
    _opacity = Tween<double>(begin: 1.0, end: 0.45).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeInOut),
    );
    _scale = Tween<double>(begin: 1.0, end: 1.3).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeInOut),
    );
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _reducedMotion = MediaQuery.disableAnimationsOf(context);
    _syncAnimation();
  }

  @override
  void didUpdateWidget(LiveDot oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.enabled != widget.enabled) {
      _syncAnimation();
    }
  }

  void _syncAnimation() {
    if (_reducedMotion || !widget.enabled) {
      _controller.stop();
      _controller.value = 0.5; // Static mid-pulse pose.
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
    return Semantics(
      liveRegion: true,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          AnimatedBuilder(
            animation: _controller,
            builder: (BuildContext context, Widget? child) {
              return Opacity(
                opacity: _opacity.value,
                child: Transform.scale(scale: _scale.value, child: child),
              );
            },
            child: const DecoratedBox(
              decoration: BoxDecoration(
                color: AppColors.brass400,
                shape: BoxShape.circle,
              ),
              child: SizedBox(width: 8, height: 8),
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          LabelCaps(text: widget.label),
        ],
      ),
    );
  }
}
