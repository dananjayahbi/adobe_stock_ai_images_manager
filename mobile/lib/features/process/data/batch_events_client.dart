import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';

import '../../../core/network/sse_parser.dart';
import '../../../core/utils/app_exception.dart';
import '../../../core/utils/platform_paths.dart';
import '../../../core/utils/ui_message.dart';
import '../domain/batch.dart';

/// Opens the raw SSE body for [path] — the injectable seam of
/// [BatchEventsClient]: production uses Dio (`ResponseType.stream`), tests
/// feed a fake `Stream<Uint8List>` directly without HTTP.
typedef SseFetch = Future<ResponseBody> Function(
  String path,
  CancelToken cancelToken,
);

/// Streams `BatchSnapshot`s from
/// `GET platformPath(platformId, 'batches/{batchId}/events')` (02 §11).
///
/// Wire format, verified live on `:8002`: frames are `data:
/// {BatchResponse JSON}\n\n`; `: ping` comments (every 15s) and the opening
/// `: stream open` comment are skipped by the shared [SseParser] (reused
/// verbatim — no parsing lives here); `event: done\ndata: {}\n\n` closes the
/// stream. Chunks are decoded with [utf8.decoder], which stitches codepoints
/// split across TCP chunks, so frames may split anywhere.
///
/// Errors surface as [AppException]s via `mapDioError` (a 404 probe before
/// the stream opens becomes [NotFoundException]). Cancelling the subscription
/// ([StreamSubscription.cancel] — what happens when the consumer/dispose
/// tears down) cancels the Dio request through a [CancelToken] so leaving
/// the screen stops the connection (03 §4 lifecycle).
class BatchEventsClient {
  BatchEventsClient(this._dio, {this.fetch});

  final Dio _dio;

  /// Test seam: when set, opens [fetch] instead of Dio's HTTP stack.
  final SseFetch? fetch;

  Stream<BatchSnapshot> watchBatch(String platformId, String batchId) {
    final String path = platformPath(platformId, 'batches/$batchId/events');
    final CancelToken cancelToken = CancelToken();
    final SseParser parser = SseParser();

    late StreamController<BatchSnapshot> controller;
    StreamSubscription<String>? byteSub;
    // Set when the consumer cancelled or we finished — late dio callbacks
    // must then stay silent instead of pushing into a dead controller.
    bool dead = false;

    Future<void> teardown() async {
      dead = true;
      final StreamSubscription<String>? active = byteSub;
      byteSub = null;
      await active?.cancel();
      if (!cancelToken.isCancelled) {
        cancelToken.cancel('watchBatch closed');
      }
    }

    void emitFrame(SseFrame frame) {
      if (dead || controller.isClosed) {
        return;
      }
      if (frame.event == 'done') {
        controller.close();
        unawaited(teardown());
        return;
      }
      final Object? decoded;
      try {
        decoded = jsonDecode(frame.data);
      } on FormatException {
        return; // empty or non-JSON frame — ignore unknown events (02 §11)
      }
      if (decoded is Map<String, Object?>) {
        controller.add(BatchSnapshot(Batch.fromJson(decoded)));
      }
    }

    Future<void> connect() async {
      try {
        final ResponseBody body = await _open(path, cancelToken);
        if (dead || controller.isClosed) {
          cancelToken.cancel('watchBatch closed before connect finished');
          return;
        }
        // `utf8.decoder.bind` (not `.transform` — Utf8Decoder is a
        // `StreamTransformer<List<int>, String>` and the covariant receiver
        // check on `Stream<Uint8List>` fails at runtime). The decoder also
        // stitches codepoints split across chunks.
        byteSub = utf8.decoder.bind(body.stream).listen(
          (String chunk) {
            for (final SseFrame frame in parser.push(chunk)) {
              emitFrame(frame);
            }
          },
          onError: (Object error) {
            if (dead || controller.isClosed) {
              return;
            }
            controller.addError(_asAppException(error));
            controller.close();
            unawaited(teardown());
          },
          onDone: () {
            // Ended without `event: done` (proxy cut / backend restart) —
            // close normally; the consumer decides whether to fall back.
            if (dead || controller.isClosed) {
              return;
            }
            controller.close();
            unawaited(teardown());
          },
          cancelOnError: true,
        );
      } catch (error) {
        if (dead || controller.isClosed) {
          return;
        }
        controller.addError(_asAppException(error));
        await teardown();
        await controller.close();
      }
    }

    controller = StreamController<BatchSnapshot>(
      onListen: () {
        unawaited(connect());
      },
      onCancel: teardown,
    );
    return controller.stream;
  }

  Future<ResponseBody> _open(String path, CancelToken cancelToken) async {
    final SseFetch? fetcher = fetch;
    if (fetcher != null) {
      return fetcher(path, cancelToken);
    }
    final Response<Object?> response = await _dio.get<Object?>(
      path,
      options: Options(responseType: ResponseType.stream),
      cancelToken: cancelToken,
    );
    final Object? data = response.data;
    if (data is ResponseBody) {
      return data;
    }
    throw const ServerException(message: 'SSE response was not streamed');
  }

  Object _asAppException(Object error) {
    if (error is AppException) {
      return error;
    }
    if (error is DioException) {
      return mapDioError(error);
    }
    return NetworkException(message: 'Live updates lost', cause: error);
  }
}
