import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'error_view.dart';
import 'skeleton_loader.dart';

/// Folds an [AsyncValue] into loading / error / data widgets (Riverpod 3
/// [AsyncValue.when]).
///
/// Defaults: [loading] → [SkeletonLoader.card], [error] → [ErrorView] wired
/// to [onRetry], data → [builder].
class AsyncView<T> extends StatelessWidget {
  const AsyncView({
    super.key,
    required this.data,
    required this.builder,
    this.onRetry,
    this.loading,
    this.error,
  });

  /// Value straight from a provider read.
  final AsyncValue<T> data;

  /// Builds the UI for a successful value.
  final Widget Function(T) builder;

  /// Wired to the default [ErrorView] retry button.
  final VoidCallback? onRetry;

  /// Replaces the default skeleton while loading.
  final Widget? loading;

  /// Replaces the default [ErrorView] on failure.
  final Widget? error;

  @override
  Widget build(BuildContext context) {
    return data.when(
      loading: () => loading ?? SkeletonLoader.card(),
      error: (Object e, StackTrace st) => error ?? ErrorView(onRetry: onRetry),
      data: builder,
    );
  }
}
