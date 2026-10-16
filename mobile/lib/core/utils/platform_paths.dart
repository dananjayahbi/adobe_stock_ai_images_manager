/// Single seam for platform URL building — feature code never
/// string-concats platform paths itself (03 §3.5).
///
/// Legacy Adobe routes are top-level today (`/api/records`); scoped routers
/// (`/api/platforms/{id}/...`) land later — flipping this one switch flips
/// the whole app.
String platformPath(String platformId, String rest) {
  // Ids get both ends trimmed; `rest` may carry a query, so only its
  // leading slashes are removed (query values stay byte-for-byte).
  final String id = _trimSlashes(platformId);
  final String resource = _trimLeading(rest);
  if (id == 'adobe_stock') {
    return '/api/$resource';
  }
  return '/api/platforms/$id/$resource';
}

/// Absolute thumbnail URL for a stored file path or bare filename.
///
/// The database keeps absolute Windows/POSIX paths
/// (`E:\storage\...\thumbs\a.jpg`, `/var/data/.../a.jpg`); only the
/// basename belongs in `{baseUrl}/thumbnails/{name}` (02 §17).
String thumbnailsUrl(String baseUrl, String pathOrBasename) {
  final String base = baseUrl.endsWith('/')
      ? baseUrl.substring(0, baseUrl.length - 1)
      : baseUrl;
  return '$base/thumbnails/${_basename(pathOrBasename)}';
}

/// Segment after the last `/` or `\`, ignoring query/fragment.
String _basename(String pathOrName) {
  final String clean = pathOrName.split('?').first.split('#').first;
  final int forward = clean.lastIndexOf('/');
  final int backward = clean.lastIndexOf(r'\');
  final int cut = forward > backward ? forward : backward;
  final String name = cut >= 0 ? clean.substring(cut + 1) : clean;
  return name.isEmpty ? clean : name;
}

/// Strips leading slashes so joins never produce `//` in the path portion.
String _trimLeading(String value) {
  int start = 0;
  final int end = value.length;
  while (start < end && value[start] == '/') {
    start++;
  }
  return value.substring(start);
}

/// Strips leading and trailing slashes (ids never carry a query).
String _trimSlashes(String value) {
  final String leading = _trimLeading(value);
  int end = leading.length;
  while (end > 0 && leading[end - 1] == '/') {
    end--;
  }
  return leading.substring(0, end);
}
