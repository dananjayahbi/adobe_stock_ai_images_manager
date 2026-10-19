import 'package:ai_stock_studio/core/network/sse_parser.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('reassembles a frame split across two pushes', () {
    final SseParser parser = SseParser();
    expect(parser.push('event: progress\ndata: {"step":'), isEmpty);
    final List<SseFrame> frames = parser.push('2}\n\n');
    expect(frames, hasLength(1));
    expect(frames.single.event, 'progress');
    expect(frames.single.data, '{"step":2}');
  });

  test('multiple frames in one chunk arrive in order', () {
    final SseParser parser = SseParser();
    final List<SseFrame> frames =
        parser.push('data: first\n\ndata: second\n\n');
    expect(frames, hasLength(2));
    expect(frames[0].event, isNull);
    expect(frames[0].data, 'first');
    expect(frames[1].event, isNull);
    expect(frames[1].data, 'second');
  });

  test('terminal event: done + data: {} parses', () {
    final SseParser parser = SseParser();
    final List<SseFrame> frames =
        parser.push('event: done\ndata: {}\n\n');
    expect(frames, hasLength(1));
    expect(frames.single.event, 'done');
    expect(frames.single.data, '{}');
  });

  test('CRLF line endings work, even split across pushes', () {
    final SseParser parser = SseParser();
    expect(parser.push('data: hello\r'), isEmpty);
    final List<SseFrame> frames = parser.push('\r\n\r\n');
    expect(frames, hasLength(1));
    expect(frames.single.data, 'hello');
  });

  test('CRLF frames and comment keep-alives', () {
    final SseParser parser = SseParser();
    final List<SseFrame> frames = parser.push(
      ': keep-alive\r\nevent: tick\r\ndata: 1\r\n\r\ndata: 2\r\n\r\n',
    );
    expect(frames, hasLength(2));
    expect(frames[0].event, 'tick');
    expect(frames[0].data, '1');
    expect(frames[1].event, isNull);
    expect(frames[1].data, '2');
  });

  test('multiple data lines join with newline; partial line carried over',
      () {
    final SseParser parser = SseParser();
    expect(parser.push('da'), isEmpty);
    expect(parser.push('ta: line-1\ndata: line-2\n'), isEmpty);
    final List<SseFrame> frames = parser.push('\n');
    expect(frames, hasLength(1));
    expect(frames.single.data, 'line-1\nline-2');
  });

  test('no trailing blank line keeps the frame buffered', () {
    final SseParser parser = SseParser();
    expect(parser.push('data: pending'), isEmpty);
    expect(parser.push('\n\n'), hasLength(1));
  });
}
