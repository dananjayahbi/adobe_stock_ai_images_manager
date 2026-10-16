/// A named backend address the app can talk to (06 §5).
///
/// Persisted as JSON in `shared_preferences` (`profiles_v1`); the session
/// cookie belonging to each profile lives separately in secure storage,
/// keyed by [id].
///
/// No Riverpod (or Flutter) imports here — this is a plain domain entity.
class ConnectionProfile {
  const ConnectionProfile({
    required this.id,
    required this.baseUrl,
    required this.label,
    this.lastStatus,
    this.lastCheckedAt,
    this.hint,
  });

  factory ConnectionProfile.fromJson(Map<String, dynamic> json) =>
      ConnectionProfile(
        id: json['id'] as String,
        label: json['label'] as String,
        baseUrl: json['baseUrl'] as String,
        lastStatus: json['lastStatus'] as String?,
        lastCheckedAt: json['lastCheckedAt'] == null
            ? null
            : DateTime.tryParse(json['lastCheckedAt'] as String),
        hint: json['hint'] as String?,
      );

  /// Stable identifier: `local`, `tunnel`, or a user-defined slug.
  final String id;

  /// Display name in the connections UI.
  final String label;

  /// Scheme + host + port, e.g. `http://192.168.1.23:8007`.
  final String baseUrl;

  /// Last health-check verdict (`ok`, `unreachable`, …), if any.
  final String? lastStatus;

  /// When [lastStatus] was recorded.
  final DateTime? lastCheckedAt;

  /// Placeholder guidance shown in the profile editor (e.g. emulator
  /// `10.0.2.2` or the quick-tunnel URL note).
  final String? hint;

  /// Returns a copy with the given non-null fields replaced; `null` keeps
  /// the previous value.
  ConnectionProfile copyWith({
    String? id,
    String? label,
    String? baseUrl,
    String? lastStatus,
    DateTime? lastCheckedAt,
    String? hint,
  }) =>
      ConnectionProfile(
        id: id ?? this.id,
        label: label ?? this.label,
        baseUrl: baseUrl ?? this.baseUrl,
        lastStatus: lastStatus ?? this.lastStatus,
        lastCheckedAt: lastCheckedAt ?? this.lastCheckedAt,
        hint: hint ?? this.hint,
      );

  Map<String, dynamic> toJson() => <String, dynamic>{
        'id': id,
        'label': label,
        'baseUrl': baseUrl,
        'lastStatus': lastStatus,
        'lastCheckedAt': lastCheckedAt?.toIso8601String(),
        'hint': hint,
      };

  @override
  bool operator ==(Object other) =>
      other is ConnectionProfile &&
      other.id == id &&
      other.label == label &&
      other.baseUrl == baseUrl &&
      other.lastStatus == lastStatus &&
      other.lastCheckedAt == lastCheckedAt &&
      other.hint == hint;

  @override
  int get hashCode =>
      Object.hash(id, label, baseUrl, lastStatus, lastCheckedAt, hint);

  @override
  String toString() => 'ConnectionProfile($id, $baseUrl)';
}
