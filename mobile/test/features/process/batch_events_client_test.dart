import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ai_stock_studio/core/utils/app_exception.dart';
import 'package:ai_stock_studio/features/process/data/batch_events_client.dart';
import 'package:ai_stock_studio/features/process/domain/batch.dart';

/// One `BatchResponse`-shaped frame payload. The name holds `·` (U+00B7,
/// two UTF-8 bytes) so a byte-split inside it proves the utf8 decoder
/// stitches codepoints across chunks.
Map<String, Object?> _batchJson(String status) => <String, Object?>{
      'id': 'b-1',
      'name': 'Raster · run',
      'media_type': 'raster',
      'steps': <Object?>[
        <String, Object?>{'key': 'ocr', 'config': <String, Object?>{}},
      ],
      'profile_id': null,
      'status': status,
      'step_progress': null,
      'error': null,
      'record_count': 3,
      'created_at': '2026-10-13T13:38:39.812348',
      'updated_at': '2026-10-13T14:02:06.870670',
      'finished_at': null,
    };

/// Splits [bytes] right between the two bytes of the first `·` (C2 B7).
List<Uint8List> _splitInsideMiddleDot(List<int> bytes) {
  for (int i = 0; i < bytes.length - 1; i++) {
    if (bytes[i] == 0xC2 && bytes[i + 1] == 0xB7) {
      return <Uint8List>[
        Uint8List.fromList(bytes.sublist(0, i + 1)),
        Uint8List.fromList(bytes.sublist(i + 1)),
      ];
    }
  }
  fail('fixture lost its middle dot');
}

void main() {
  test(
      'streams snapshots across mid-frame chunk splits, ignores ping comments '
      'and junk data, closes on done', () async {
    final String frame1 = 'data: ${jsonEncode(_batchJson('draft'))}\n\n';
    final String ping = ': ping\n\n';
    final String junk = 'data: not-json\n\n';
    final String frame2 = 'data: ${jsonEncode(_batchJson('running'))}\n\n';
    const String doneOpen = 'event: do';
    const String doneRest = 'ne\ndata: {}\n\n';

    // Chunk plan: frame1 cut mid-JSON; ping; junk; frame2 cut inside the
    // middle-dot codepoint; done event cut mid-word.
    final List<int> bytes1 = utf8.encode(frame1);
    final List<Uint8List> chunks = <Uint8List>[
      Uint8List.fromList(bytes1.sublist(0, bytes1.length ~/ 2)),
      Uint8List.fromList(bytes1.sublist(bytes1.length ~/ 2)),
      Uint8List.fromList(utf8.encode(ping)),
      Uint8List.fromList(utf8.encode(junk)),
      ..._splitInsideMiddleDot(utf8.encode(frame2)),
      Uint8List.fromList(utf8.encode(doneOpen)),
      Uint8List.fromList(utf8.encode(doneRest)),
    ];

    final StreamController<Uint8List> wire = StreamController<Uint8List>();
    String? seenPath;
    final BatchEventsClient client = BatchEventsClient(
      Dio(),
      fetch: (String path, CancelToken cancelToken) async {
        seenPath = path;
        return ResponseBody(
          wire.stream,
          200,
          headers: <String, List<String>>{
            Headers.contentTypeHeader: <String>['text/event-stream'],
          },
        );
      },
    );

    for (final Uint8List chunk in chunks) {
      wire.add(chunk);
    }
    // Listen first, then close — `close()`'s future only completes once a
    // listener has consumed the done event.
    final Future<List<BatchSnapshot>> collected =
        client.watchBatch('adobe_stock', 'b-1').toList();
    await wire.close();

    final List<BatchSnapshot> events = await collected;

    expect(seenPath, '/api/batches/b-1/events'); // platformPath, adobe_stock
    expect(events, hasLength(2)); // ping + junk produced nothing
    expect(events.first.batch.status, 'draft');
    expect(events.last.batch.status, 'running');
    expect(events.last.batch.name, 'Raster · run'); // stitched codepoint
    expect(events.last.batch.recordCount, 3);
  });

  test('other platforms ride the platformPath prefix', () async {
    final StreamController<Uint8List> wire = StreamController<Uint8List>();
    String? seenPath;
    final BatchEventsClient client = BatchEventsClient(
      Dio(),
      fetch: (String path, CancelToken cancelToken) async {
        seenPath = path;
        return ResponseBody(wire.stream, 200);
      },
    );
    final Future<List<BatchSnapshot>> collected =
        client.watchBatch('freepik', 'b-9').toList();
    await pumpEventQueue(); // connect() attaches its listener
    await wire.close(); // completes now that the stream is being consumed
    await collected;
    expect(seenPath, '/api/platforms/freepik/batches/b-9/events');
  });

  test('open failure maps DioException 404 to NotFoundException', () async {
    final BatchEventsClient client = BatchEventsClient(
      Dio(),
      fetch: (String path, CancelToken cancelToken) async {
        throw DioException(
          requestOptions: RequestOptions(path: path),
          response: Response<dynamic>(
            requestOptions: RequestOptions(path: path),
            statusCode: 404,
          ),
          type: DioExceptionType.badResponse,
        );
      },
    );

    await expectLater(
      client.watchBatch('adobe_stock', 'gone').toList(),
      throwsA(isA<NotFoundException>()),
    );
  });

  test('mid-stream DioException surfaces as a mapped AppException', () async {
    final StreamController<Uint8List> wire = StreamController<Uint8List>();
    final BatchEventsClient client = BatchEventsClient(
      Dio(),
      fetch: (String path, CancelToken cancelToken) async =>
          ResponseBody(wire.stream, 200),
    );

    final Future<List<BatchSnapshot>> collected =
        client.watchBatch('adobe_stock', 'b-2').toList();
    // Let connect() open the body, then break the socket mid-run.
    await pumpEventQueue();
    wire.addError(
      DioException(
        requestOptions: RequestOptions(path: '/api/batches/b-2/events'),
        type: DioExceptionType.connectionError,
        error: 'cut',
      ),
    );

    await expectLater(collected, throwsA(isA<AppException>()));
  });

  test('cancelling the subscription cancels the dio CancelToken', () async {
    final StreamController<Uint8List> wire = StreamController<Uint8List>();
    CancelToken? seenToken;
    final BatchEventsClient client = BatchEventsClient(
      Dio(),
      fetch: (String path, CancelToken cancelToken) async {
        seenToken = cancelToken;
        return ResponseBody(wire.stream, 200);
      },
    );

    final StreamSubscription<BatchSnapshot> sub =
        client.watchBatch('adobe_stock', 'b-3').listen((BatchSnapshot _) {});
    await pumpEventQueue();
    expect(seenToken, isNotNull);
    expect(seenToken!.isCancelled, isFalse); // still connected

    await sub.cancel();
    expect(seenToken!.isCancelled, isTrue); // leaving the screen kills it
    unawaited(wire.close()); // no listener remains — never await this close
  });
}
