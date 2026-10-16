import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Process-wide `studio_session=<value>` request-header replay value
/// (name/value pair, no attributes).
///
/// The auth cookie jar publishes here whenever a login response refreshes
/// the session, and image loaders that bypass Dio read it to attach the
/// `Cookie` header themselves (02 §17 note 2).
final sessionCookieHeaderProvider =
    NotifierProvider<SessionCookieHeaderNotifier, String?>(
  SessionCookieHeaderNotifier.new,
);

class SessionCookieHeaderNotifier extends Notifier<String?> {
  @override
  String? build() => null;

  /// Updates the replay value; `null` clears it (logout / 401).
  void set(String? value) => state = value;
}
