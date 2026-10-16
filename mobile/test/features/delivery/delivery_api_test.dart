import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ai_stock_studio/features/delivery/data/delivery_api.dart';
import 'package:ai_stock_studio/features/delivery/domain/delivery_item.dart';

/// Records every request Dio sends (method + final path + decoded body) and
/// answers with canned payloads, so the tests pin the *wire* contract —
/// platformPath output included — exactly as the backend sees it.
class _RecordingAdapter implements HttpClientAdapter {
  final List<_Request> requests = <_Request>[];

  /// JSON payload for JSON endpoints.
  Object? payload = <String, Object?>{};

  /// Raw body for byte endpoints (csv / bundle).
  Uint8List bytes = Uint8List.fromList(<int>[]);

  Map<String, List<String>> headers = <String, List<String>>{};

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(
      _Request(options.method, options.uri, _decodeBody(options.data)),
    );
    final Map<String, List<String>> headers = <String, List<String>>{
      Headers.contentTypeHeader: <String>[
        options.responseType == ResponseType.bytes
            ? 'application/octet-stream'
            : Headers.jsonContentType,
      ],
      ...this.headers,
    };
    if (options.responseType == ResponseType.bytes) {
      return ResponseBody.fromBytes(bytes, 200, headers: headers);
    }
    return ResponseBody.fromString(
      jsonEncode(payload),
      200,
      headers: headers,
    );
  }

  /// Request data reaches the adapter as the original Dart object, a JSON
  /// string, or encoded bytes depending on Dio's transform pass — normalise
  /// all three to a decoded object for assertions.
  Object? _decodeBody(Object? data) {
    if (data == null) return null;
    if (data is String) {
      try {
        return jsonDecode(data);
      } on FormatException {
        return data;
      }
    }
    if (data is List<int>) {
      try {
        return jsonDecode(utf8.decode(data));
      } on FormatException {
        return data;
      }
    }
    return data;
  }

  @override
  void close({bool force = false}) {}
}

class _Request {
  const _Request(this.method, this.uri, this.body);

  final String method;
  final Uri uri;
  final Object? body;

  /// `path?query` as the endpoint contract writes it.
  String get target => uri.hasQuery ? '${uri.path}?${uri.query}' : uri.path;
}

void main() {
  late _RecordingAdapter adapter;
  late DeliveryApi api;

  setUp(() {
    adapter = _RecordingAdapter();
    final Dio dio = Dio()..httpClientAdapter = adapter;
    api = DeliveryApi(dio);
  });

  group('adobe_stock keeps the legacy top-level paths (platformPath)', () {
    test('csv preview — POST + CsvExportRequest defaults', () async {
      await api.csvPreview('adobe_stock', recordIds: null, onlyReady: true);

      final _Request request = adapter.requests.single;
      expect(request.method, 'POST');
      expect(request.target, '/api/assets/csv/preview');
      expect(request.body, <String, Object?>{
        'record_ids': null,
        'only_ready': true,
      });
    });

    test('csv export — POST + CsvExportRequest defaults', () async {
      await api.csvExport('adobe_stock', recordIds: null, onlyReady: true);

      final _Request request = adapter.requests.single;
      expect(request.method, 'POST');
      expect(request.target, '/api/assets/csv');
      expect(request.body, <String, Object?>{
        'record_ids': null,
        'only_ready': true,
      });
    });

    test('bundle — POST + explicit selection, only_ready false', () async {
      await api.bundle('adobe_stock', recordIds: <String>['r1', 'r2']);

      final _Request request = adapter.requests.single;
      expect(request.method, 'POST');
      expect(request.target, '/api/assets/bundle');
      expect(request.body, <String, Object?>{
        'record_ids': <String>['r1', 'r2'],
        'only_ready': false,
      });
    });

    test('force-accept — POST {record_ids[], reason}', () async {
      await api.forceAccept(
        'adobe_stock',
        recordIds: <String>['r1'],
        reason: 'operator overrode the score',
      );

      final _Request request = adapter.requests.single;
      expect(request.method, 'POST');
      expect(request.target, '/api/assets/force-accept');
      expect(request.body, <String, Object?>{
        'record_ids': <String>['r1'],
        'reason': 'operator overrode the score',
      });
    });

    test('rename — POST {items[{record_id, name}], regenerate}', () async {
      await api.rename(
        'adobe_stock',
        items: <RenameEntry>[
          const RenameEntry(recordId: 'r1', name: 'sunrise-lake.jpg'),
        ],
        regenerate: false,
      );

      final _Request request = adapter.requests.single;
      expect(request.method, 'POST');
      expect(request.target, '/api/assets/rename');
      expect(request.body, <String, Object?>{
        'items': <Object?>[
          <String, Object?>{'record_id': 'r1', 'name': 'sunrise-lake.jpg'},
        ],
        'regenerate': false,
      });
    });

    test('rename-suggest — same body shape, dry run path', () async {
      await api.renameSuggest(
        'adobe_stock',
        items: <RenameEntry>[
          const RenameEntry(recordId: 'r1', name: ''),
        ],
        regenerate: true,
      );

      final _Request request = adapter.requests.single;
      expect(request.method, 'POST');
      expect(request.target, '/api/assets/rename-suggest');
      expect(request.body, <String, Object?>{
        'items': <Object?>[
          <String, Object?>{'record_id': 'r1', 'name': ''},
        ],
        'regenerate': true,
      });
    });

    test('apply-suggested-names — same body shape', () async {
      await api.applySuggestedNames(
        'adobe_stock',
        items: <RenameEntry>[
          const RenameEntry(recordId: 'r1', name: ''),
        ],
        regenerate: false,
      );

      final _Request request = adapter.requests.single;
      expect(request.method, 'POST');
      expect(request.target, '/api/assets/apply-suggested-names');
      expect(request.body, <String, Object?>{
        'items': <Object?>[
          <String, Object?>{'record_id': 'r1', 'name': ''},
        ],
        'regenerate': false,
      });
    });

    test('candidates — GET records listing at max page size', () async {
      await api.candidates('adobe_stock');

      final _Request request = adapter.requests.single;
      expect(request.method, 'GET');
      expect(request.target, '/api/records?limit=500');
      expect(request.body, isNull);
    });

    test('leading slashes never double up', () async {
      await api.csvPreview('/adobe_stock/', recordIds: null, onlyReady: true);
      expect(adapter.requests.single.target, '/api/assets/csv/preview');
    });
  });

  group('selection semantics mirror frontend-new/src/lib/delivery.ts', () {
    test('explicit selection travels with only_ready false', () async {
      await api.csvPreview('adobe_stock', recordIds: <String>['a'], onlyReady: false);
      await api.csvExport('adobe_stock', recordIds: <String>['a'], onlyReady: false);

      expect(
        adapter.requests.map<Object?>(( _Request r) => r.body).toList(),
        <Object?>[
          <String, Object?>{'record_ids': <String>['a'], 'only_ready': false},
          <String, Object?>{'record_ids': <String>['a'], 'only_ready': false},
        ],
      );
    });

    test('record_ids rides as JSON null when nothing is selected', () async {
      await api.csvPreview('adobe_stock', recordIds: null, onlyReady: true);
      final Map<Object?, Object?> body =
          adapter.requests.single.body! as Map<Object?, Object?>;
      expect(body.containsKey('record_ids'), isTrue);
      expect(body['record_ids'], isNull);
    });
  });

  group('other platforms ride the scoped prefix (02 §2 shape)', () {
    test('freepik delivery endpoints', () async {
      await api.csvPreview('freepik', recordIds: null, onlyReady: true);
      await api.forceAccept('freepik', recordIds: <String>['r'], reason: 'x');
      await api.candidates('freepik');

      expect(
        adapter.requests.map<String>((_Request r) => r.target).toList(),
        <String>[
          '/api/platforms/freepik/assets/csv/preview',
          '/api/platforms/freepik/assets/force-accept',
          '/api/platforms/freepik/records?limit=500',
        ],
      );
    });
  });

  group('byte endpoints return bytes + disposition headers', () {
    test('csv export hands the response back untouched', () async {
      adapter
        ..bytes = Uint8List.fromList(utf8.encode('Filename,Title\r\na,b\r\n'))
        ..headers = <String, List<String>>{
          'content-disposition': <String>[
            'attachment; filename="adobe-stock-metadata.csv"',
          ],
          'x-csv-row-count': <String>['1'],
        };

      final Response<List<int>> response = await api.csvExport(
        'adobe_stock',
        recordIds: null,
        onlyReady: true,
      );

      expect(response.statusCode, 200);
      expect(utf8.decode(response.data!), contains('Filename,Title'));
      expect(
        response.headers.map['content-disposition']?.first,
        contains('adobe-stock-metadata.csv'),
      );
    });
  });
}
