/// One dispatched server-sent event.
///
/// [event] is null when the frame only carried `data:` lines (SSE default
/// event name); [data] joins multiple `data:` lines with `\n` per spec.
class SseFrame {
  const SseFrame({this.event, required this.data});

  final String? event;
  final String data;
}

/// Incremental `text/event-stream` parser (02 §17 note 3).
///
/// Feed raw socket chunks with [push]; complete frames (terminated by a
/// blank line) come back immediately, partial input is carried over to the
/// next push. Handles frames split across chunk boundaries, CRLF/LF/CR
/// line endings, and `:` keep-alive comments.
class SseParser {
  final StringBuffer _pending = StringBuffer();

  /// Consumes [chunk] and returns every frame completed by it.
  List<SseFrame> push(String chunk) {
    if (chunk.isEmpty) {
      return const [];
    }
    _pending.write(chunk);
    final String text = _normalize(_pending.toString());
    _pending.clear();
    _pending.write(text);

    final List<String> blocks = text.split('\n\n');
    // Last element is the (possibly empty) partial block — keep it.
    final List<String> complete =
        blocks.sublist(0, blocks.length - 1);
    final String remainder = blocks.last;
    _pending
      ..clear()
      ..write(remainder);

    final List<SseFrame> frames = [];
    for (final String block in complete) {
      final SseFrame? frame = _parseBlock(block);
      if (frame != null) {
        frames.add(frame);
      }
    }
    return frames;
  }

  /// Normalizes line endings without breaking a `\r`/`\n` pair that is
  /// itself split across two pushes.
  String _normalize(String raw) {
    String text = raw.replaceAll('\r\n', '\n');
    String tail = '';
    if (text.endsWith('\r')) {
      // Could be the first half of a CRLF — wait for the next chunk.
      text = text.substring(0, text.length - 1);
      tail = '\r';
    }
    text = text.replaceAll('\r', '\n');
    return '$text$tail';
  }

  /// Parses one blank-line-terminated block; null for empty/no-field
  /// blocks (e.g. keep-alive comments only).
  SseFrame? _parseBlock(String block) {
    String? event;
    final List<String> dataLines = [];
    bool sawField = false;

    for (final String line in block.split('\n')) {
      if (line.isEmpty || line.startsWith(':')) {
        continue; // padding or `: keep-alive` comment
      }
      final int colon = line.indexOf(':');
      final String field = colon < 0 ? line : line.substring(0, colon);
      String value = colon < 0 ? '' : line.substring(colon + 1);
      if (value.startsWith(' ')) {
        value = value.substring(1); // one space per SSE spec
      }
      switch (field) {
        case 'event':
          event = value;
          sawField = true;
        case 'data':
          dataLines.add(value);
          sawField = true;
        case 'id':
        case 'retry':
          sawField = true;
        default:
          break; // unknown fields are ignored
      }
    }

    if (!sawField) {
      return null;
    }
    return SseFrame(event: event, data: dataLines.join('\n'));
  }
}
