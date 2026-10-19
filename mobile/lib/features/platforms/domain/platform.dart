/// Platform catalogue entries — the shape `backend/platforms/routers.py`
/// returns verbatim (`_serialize`): `{id, name, tagline, status, route}`.
library;

/// One platform as served by `GET /api/platforms/` (02 §2).
///
/// [status] is the backend's literal value: `available` or `coming_soon`;
/// [available] is the UI-facing derivation so widgets never string-compare.
class PlatformEntry {
  const PlatformEntry({
    required this.id,
    required this.name,
    required this.tagline,
    required this.status,
    required this.route,
  });

  /// Parses one item of the catalogue JSON. Every field is a `str` on the
  /// backend, but missing keys fall back defensively rather than crash the
  /// picker (03 §4: bad payloads surface as visible state, not exceptions).
  factory PlatformEntry.fromJson(Map<String, dynamic> json) {
    return PlatformEntry(
      id: (json['id'] as String?) ?? '',
      name: (json['name'] as String?) ?? '',
      tagline: (json['tagline'] as String?) ?? '',
      status: (json['status'] as String?) ?? 'coming_soon',
      route: (json['route'] as String?) ?? '',
    );
  }

  /// Stable slug used for routing and the active-platform provider.
  final String id;

  /// Display name (`Adobe Stock`).
  final String name;

  /// One-line marketing copy shown under the name.
  final String tagline;

  /// Raw backend status: `available` | `coming_soon`.
  final String status;

  /// Web parity route (`/adobe-stock`) — informational on mobile; the app
  /// routes through `/home` + `/coming-soon/:platformId` instead.
  final String route;

  /// Whether the workspace can be opened today.
  bool get available => status == 'available';

  Map<String, dynamic> toJson() => <String, dynamic>{
        'id': id,
        'name': name,
        'tagline': tagline,
        'status': status,
        'route': route,
      };

  @override
  bool operator ==(Object other) =>
      other is PlatformEntry &&
      other.id == id &&
      other.name == name &&
      other.tagline == tagline &&
      other.status == status &&
      other.route == route;

  @override
  int get hashCode => Object.hash(id, name, tagline, status, route);

  @override
  String toString() => 'PlatformEntry($id, $status)';
}
