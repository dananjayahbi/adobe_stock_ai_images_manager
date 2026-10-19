/// The signed-in account reported by the auth endpoints.
///
/// Backend contract (`backend/routers/auth.py`): both `POST /api/auth/login`
/// and `GET /api/auth/me` answer `{"user": {"username": "..."}}`; a missing or
/// invalid cookie makes `/me` answer `401 {"detail": "Not authenticated"}`.
/// JSON parsing lives in `data/` — this entity stays pure (03 §3.1).
class UserSession {
  const UserSession({required this.isAuthenticated, this.username});

  /// An unauthenticated (guest) session — the local probe said "no cookie".
  const UserSession.unauthenticated() : this(isAuthenticated: false);

  /// True when the payload came from a successful session probe.
  final bool isAuthenticated;

  /// The single local account name, when authenticated.
  final String? username;

  @override
  String toString() =>
      'UserSession(isAuthenticated: $isAuthenticated, username: $username)';
}
