import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/theme/tokens.dart';
import '../../../core/utils/app_exception.dart';
import '../../../core/utils/ui_message.dart';
import '../../../core/widgets/error_view.dart';
import '../../../core/widgets/primary_button.dart';
import 'auth_controller.dart';

/// The credentials card content for `/login` (05 §2.2): visible labels,
/// autofill hints, obscure toggle, keyboard-done submit, loading state and
/// errors rendered *under the form*, never as a detached banner.
class LoginForm extends ConsumerStatefulWidget {
  const LoginForm({super.key, this.onAuthenticated});

  /// Fires after a successful [AuthController.login] — the screen swaps this
  /// for `context.go('/hub')`; tests use it as a navigation probe.
  final VoidCallback? onAuthenticated;

  @override
  ConsumerState<LoginForm> createState() => _LoginFormState();
}

class _LoginFormState extends ConsumerState<LoginForm> {
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  final TextEditingController _usernameController = TextEditingController();
  final TextEditingController _passwordController = TextEditingController();

  bool _obscurePassword = true;
  bool _submitting = false;
  AppException? _error;

  @override
  void dispose() {
    _usernameController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_submitting) return;
    if (!(_formKey.currentState?.validate() ?? false)) return;
    FocusScope.of(context).unfocus();
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      await ref.read(authControllerProvider.notifier).login(
            _usernameController.text.trim(),
            _passwordController.text,
          );
      if (!mounted) return;
      widget.onAuthenticated?.call();
    } on AppException catch (e) {
      if (!mounted) return;
      setState(() => _error = e);
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AutofillGroup(
      child: Form(
        key: _formKey,
        child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          TextFormField(
            controller: _usernameController,
            enabled: !_submitting,
            autofillHints: const [AutofillHints.username],
            textInputAction: TextInputAction.next,
            decoration: const InputDecoration(labelText: 'Username'),
            validator: (value) =>
                (value == null || value.trim().isEmpty) ? 'Required' : null,
            onFieldSubmitted: (_) => _submit(),
          ),
          const SizedBox(height: AppSpacing.md),
          TextFormField(
            controller: _passwordController,
            enabled: !_submitting,
            obscureText: _obscurePassword,
            autofillHints: const [AutofillHints.password],
            textInputAction: TextInputAction.done,
            decoration: InputDecoration(
              labelText: 'Password',
              suffixIcon: IconButton(
                tooltip: _obscurePassword ? 'Show password' : 'Hide password',
                constraints:
                    const BoxConstraints(minWidth: 44, minHeight: 44),
                onPressed: () =>
                    setState(() => _obscurePassword = !_obscurePassword),
                icon: Icon(
                  _obscurePassword
                      ? Icons.visibility_outlined
                      : Icons.visibility_off_outlined,
                ),
              ),
            ),
            validator: (value) => (value == null || value.isEmpty)
                ? 'Required'
                : null,
            onFieldSubmitted: (_) => _submit(),
          ),
          if (_error != null) ...[
            const SizedBox(height: AppSpacing.md),
            _FormError(error: _error!, onRetry: _submit),
          ],
          const SizedBox(height: AppSpacing.lg),
          PrimaryButton(
            label: 'Sign in',
            loading: _submitting,
            expanded: true,
            onPressed: _submitting ? null : _submit,
          ),
        ],
      ),
    ),
  );
  }
}

/// Error display pinned directly under the failing form (04 error-near-field).
class _FormError extends StatelessWidget {
  const _FormError({required this.error, required this.onRetry});

  final AppException error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    if (error is AuthException) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            "Those keys didn't fit.",
            style: theme.textTheme.bodyMedium?.copyWith(
              color: theme.colorScheme.error,
            ),
          ),
          const SizedBox(height: AppSpacing.xs),
          Text(uiMessageFor(error), style: theme.textTheme.bodySmall),
        ],
      );
    }
    if (error is NetworkException) {
      // Offline: inline retry hint instead of a full-screen error (05 §2.2).
      return ErrorView(message: uiMessageFor(error), onRetry: onRetry);
    }
    return Text(
      uiMessageFor(error),
      style: theme.textTheme.bodyMedium?.copyWith(
        color: theme.colorScheme.error,
      ),
    );
  }
}
