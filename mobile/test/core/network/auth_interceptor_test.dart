import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:ai_stock_studio/core/network/auth_interceptor.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

/// Adapter that answers every request with a canned status code.
class _StatusAdapter implements HttpClientAdapter {
  int statusCode = 401;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    return ResponseBody.fromString(
      jsonEncode(<String, Object?>{'detail': 'boom'}),
      statusCode,
      headers: <String, List<String>>{
        Headers.contentTypeHeader: [Headers.jsonContentType],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

void main() {
  late _StatusAdapter adapter;
  late int calls;
  late List<Completer<void>> blockers;

  setUp(() {
    adapter = _StatusAdapter();
    calls = 0;
    blockers = <Completer<void>>[];
  });

  AuthInterceptor buildInterceptor({bool block = false}) {
    return AuthInterceptor(
      onUnauthorized: () {
        calls++;
        if (block) {
          final Completer<void> completer = Completer<void>();
          blockers.add(completer);
          return completer.future;
        }
        return Future<void>.value();
      },
    );
  }

  Dio dioWith(AuthInterceptor interceptor) {
    final Dio dio = Dio()..httpClientAdapter = adapter;
    dio.interceptors.add(interceptor);
    return dio;
  }

  /// Requests [path] and returns the propagated [DioException] — the
  /// interceptor must never swallow it.
  Future<DioException> expectError(Dio dio, String path) async {
    try {
      await dio.get(path);
      fail('Expected a DioException for $path');
    } on DioException catch (e) {
      return e;
    }
  }

  test('401 on an API route triggers onUnauthorized exactly once',
      () async {
    final Dio dio = dioWith(buildInterceptor());
    adapter.statusCode = 401;
    final DioException error = await expectError(dio, '/api/records');
    expect(error.response?.statusCode, 401);
    await pumpEventQueue();
    expect(calls, 1);
  });

  test('duplicate 401 while the handler is in flight never double-calls',
      () async {
    final Dio dio = dioWith(buildInterceptor(block: true));
    adapter.statusCode = 401;
    await expectError(dio, '/api/records'); // calls #1, guard engaged
    await expectError(dio, '/api/records'); // same propagation → suppressed
    expect(calls, 1);

    // Once the handler finishes, the next 401 fires again (re-armed).
    blockers.first.complete();
    await pumpEventQueue();
    await expectError(dio, '/api/records');
    expect(calls, 2);

    blockers.last.complete();
    await pumpEventQueue();
  });

  test('401 on /api/auth/login does NOT trigger onUnauthorized',
      () async {
    final Dio dio = dioWith(buildInterceptor());
    adapter.statusCode = 401;
    final DioException error =
        await expectError(dio, '/api/auth/login');
    expect(error.response?.statusCode, 401);
    await pumpEventQueue();
    expect(calls, 0);
  });

  test('500 does NOT trigger onUnauthorized', () async {
    final Dio dio = dioWith(buildInterceptor());
    adapter.statusCode = 500;
    await expectError(dio, '/api/records');
    await pumpEventQueue();
    expect(calls, 0);
  });

  test('resetGuard re-arms the guard for the next case', () async {
    final AuthInterceptor interceptor = buildInterceptor(block: true);
    final Dio dio = dioWith(interceptor);
    adapter.statusCode = 401;
    await expectError(dio, '/api/records');
    expect(calls, 1);
    interceptor.resetGuard();
    await expectError(dio, '/api/records');
    expect(calls, 2);
    for (final Completer<void> completer in blockers) {
      if (!completer.isCompleted) {
        completer.complete();
      }
    }
    await pumpEventQueue();
  });
}
