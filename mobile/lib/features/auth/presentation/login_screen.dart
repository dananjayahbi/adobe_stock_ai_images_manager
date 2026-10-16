import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../../app/theme/tokens.dart';
import '../../../core/widgets/app_card.dart';
import '../../../core/widgets/label_caps.dart';
import '../../../core/widgets/stamp_in.dart';
import 'login_form.dart';
import 'login_profile_switcher.dart';

/// Full-screen `/login` composition (05 §2.2): leather stage, stamp-in
/// wordmark + eyebrow, and the AppCard-embedded [LoginForm].
class LoginScreen extends StatelessWidget {
  const LoginScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final TextTheme textTheme = Theme.of(context).textTheme;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(AppSpacing.xl),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 480),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  StampIn(
                    child: Column(
                      children: [
                        const LabelCaps(text: 'EST. LOCAL'),
                        const SizedBox(height: AppSpacing.sm),
                        Text(
                          'AI STOCK STUDIO',
                          textAlign: TextAlign.center,
                          style: textTheme.displaySmall,
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: AppSpacing.xl),
                  AppCard(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        // Pre-auth escape hatch: switch to a reachable profile
                        // before signing in (fresh installs default to
                        // localhost, which is the phone itself).
                        const LoginProfileSwitcher(),
                        const SizedBox(height: AppSpacing.md),
                        const Divider(
                          height: 1,
                          thickness: 1,
                          color: AppColors.parchment300,
                        ),
                        const SizedBox(height: AppSpacing.md),
                        LoginForm(onAuthenticated: () => context.go('/hub')),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
