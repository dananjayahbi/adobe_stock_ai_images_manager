/// Build environment selected with `--dart-define=APP_ENV=dev|prod`.
///
/// Defaults to [AppEnv.dev] so local development works without flags
/// (mobile-plan/03 §4).
enum AppEnv {
  dev,
  prod;

  /// Raw `APP_ENV` dart-define value for this build.
  static const String rawValue = String.fromEnvironment(
    'APP_ENV',
    defaultValue: 'dev',
  );

  /// Resolved environment. Unknown values fall back to [AppEnv.dev].
  static AppEnv get current {
    switch (rawValue) {
      case 'prod':
        return AppEnv.prod;
      case 'dev':
        return AppEnv.dev;
      default:
        return AppEnv.dev;
    }
  }

  bool get isDev => this == AppEnv.dev;

  bool get isProd => this == AppEnv.prod;
}
