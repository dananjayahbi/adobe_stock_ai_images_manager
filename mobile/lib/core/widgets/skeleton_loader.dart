import 'package:flutter/material.dart';

import 'package:ai_stock_studio/app/theme/tokens.dart';

/// Parchment block with a looping opacity shimmer (04 §3: 1200 ms,
/// 0.4→0.7, easeInOut).
///
/// The shimmer pauses into a static block when
/// [MediaQuery.disableAnimations] is on. Named factories cover the common
/// grid tile, list row and card shapes.
class SkeletonLoader extends StatefulWidget {
  const SkeletonLoader({super.key, this.width, this.height, this.radius});

  /// Square placeholder sized for a gallery tile.
  factory SkeletonLoader.tile({double size = 88}) {
    return SkeletonLoader(
      width: size,
      height: size,
      radius: const BorderRadius.all(Radius.circular(AppRadii.sm)),
    );
  }

  /// Full-width card placeholder (also [AsyncView]'s default loading state).
  factory SkeletonLoader.card() {
    return const SkeletonLoader(
      width: double.infinity,
      height: 120,
      radius: BorderRadius.all(Radius.circular(AppRadii.md)),
    );
  }

  /// Full-width list-row placeholder.
  factory SkeletonLoader.row() {
    return const SkeletonLoader(
      width: double.infinity,
      height: 56,
      radius: BorderRadius.all(Radius.circular(AppRadii.sm)),
    );
  }

  /// Width of the block; `null` fills the incoming constraints.
  final double? width;

  /// Height of the block; `null` fills the incoming constraints.
  final double? height;

  /// Corner radius; `null` keeps hard corners.
  final BorderRadius? radius;

  @override
  State<SkeletonLoader> createState() => _SkeletonLoaderState();
}

class _SkeletonLoaderState extends State<SkeletonLoader>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _shimmer;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    );
    _shimmer = Tween<double>(begin: 0.4, end: 0.7).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeInOut),
    );
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (MediaQuery.disableAnimationsOf(context)) {
      if (_controller.isAnimating) {
        _controller.stop();
      }
      if (_controller.value == 0) {
        // Static mid-shimmer block for reduced motion.
        _controller.value = 0.5;
      }
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
      label: 'Loading',
      child: AnimatedBuilder(
        animation: _shimmer,
        builder: (BuildContext context, Widget? child) {
          return SizedBox(
            width: widget.width,
            height: widget.height,
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: AppColors.parchment300.withValues(alpha: _shimmer.value),
                borderRadius: widget.radius,
              ),
            ),
          );
        },
      ),
    );
  }
}
