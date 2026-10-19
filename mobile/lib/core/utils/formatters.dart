// Locale-independent display formatting helpers.
//
// Deliberately string-built (no `intl`) so output is deterministic in
// tests and identical on every device locale.

/// Compact count: `999`, `1.2k`, `3.4M`, `12M`.
String formatCount(int count) {
  if (count.abs() >= 1000000) {
    return '${_trimZero(count / 1000000)}M';
  }
  if (count.abs() >= 1000) {
    return '${_trimZero(count / 1000)}k';
  }
  return '$count';
}

/// Human byte size: `512 B`, `1.5 KB`, `2.3 MB`, `1.0 GB`.
String formatBytes(int bytes) {
  if (bytes < 1024) {
    return '$bytes B';
  }
  final double kilobytes = bytes / 1024;
  if (kilobytes < 1024) {
    return '${kilobytes.toStringAsFixed(1)} KB';
  }
  final double megabytes = kilobytes / 1024;
  if (megabytes < 1024) {
    return '${megabytes.toStringAsFixed(1)} MB';
  }
  return '${(megabytes / 1024).toStringAsFixed(1)} GB';
}

/// Fixed `YYYY-MM-DD HH:MM` stamp (local fields of [dt], no locale).
String formatDateTime(DateTime dt) {
  final String date =
      '${dt.year.toString().padLeft(4, '0')}-'
      '${dt.month.toString().padLeft(2, '0')}-'
      '${dt.day.toString().padLeft(2, '0')}';
  final String time =
      '${dt.hour.toString().padLeft(2, '0')}:'
      '${dt.minute.toString().padLeft(2, '0')}';
  return '$date $time';
}

/// Drops a trailing `.0` so `1.0k` renders as `1k`.
String _trimZero(double value) {
  final String text = value.toStringAsFixed(1);
  return text.endsWith('.0')
      ? text.substring(0, text.length - 2)
      : text;
}
