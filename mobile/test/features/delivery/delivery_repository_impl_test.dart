import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ai_stock_studio/core/utils/app_exception.dart';
import 'package:ai_stock_studio/features/delivery/data/delivery_repository_impl.dart';
import 'package:ai_stock_studio/features/delivery/domain/delivery_item.dart';
import 'package:ai_stock_studio/features/delivery/domain/delivery_repository.dart';

/// Captured live from `GET /api/records?limit=2&stage=METADATA_READY`
/// (backend/routers/records.py) on 2026-10-16; row two trimmed to the
/// dashboard-style minimum to prove missing fields parse defensively.
const String kCandidatesJson = r'''
{"items":[
 {"id":"0b91ca23-c3ed-4312-a4fc-74cd0033a240",
  "filename":"Wire_loop_trimming_tool_2K_20261013092634.jpg",
  "stage":"METADATA_READY",
  "upload_filename":"sculpting-tool-with-wooden-handle-and-wire-loop.jpg",
  "download_name":"sculpting-tool-with-wooden-handle-and-wire-loop.jpg",
  "generated_title":"Sculpting tool with wooden handle and wire loop",
  "acceptance_score":0.9100000000000001,"is_used":true},
 {"id":"e20aa872-3544-4352-8fc0-96c5a1a05277",
  "filename":"Acoustic_guitar_bridge_pins_arrangement_2K_20261013092129.jpg",
  "stage":"METADATA_READY"}],
"total":161,"page":1,"page_size":2}
''';

/// Captured live from `POST /api/assets/csv/preview {"only_ready":true}`
/// — real header + first rows of the 142-row deliverable set (trimmed).
const String kPreviewJson = r'''
{"csv_text":"Filename,Title,Keywords,Category,Releases\r\nvintage-cast-iron-hand-coffee-grinder-with-brass-handle.jpg,Vintage cast iron hand coffee grinder with brass handle,\"white background, coffee grinder, cast iron, vintage, antique, manual grinder\",7,\r\nindustrial-cage-pendant-light-with-vintage-bulb.jpg,Industrial cage pendant light with vintage bulb,\"white background, pendant light, cage lamp, industrial lamp\",2,\r\n",
"row_count":142,"skipped":[],"warnings":[]}
''';

/// Captured live from `POST /api/assets/csv/preview` with two REFINED ids
/// (`only_ready:false`) — real warnings for missing generated titles.
const String kPreviewWarningsJson = r'''
{"csv_text":"Filename,Title,Keywords,Category,Releases\r\nmammoth_tusk_cross-section_slice_2k_20261013092333.jpg,mammoth_tusk_cross section_slice_2k_20261013092333,,8,\r\nmetal_moxa_roll_holder_2k_20261013091833.jpg,metal_moxa_roll_holder_2k_20261013091833,,8,\r\n",
"row_count":2,"skipped":[],
"warnings":["mammoth_tusk_cross-section_slice_2k_20261013092333.jpg: no generated title; used the filename as the title.","metal_moxa_roll_holder_2k_20261013091833.jpg: no generated title; used the filename as the title."]}
''';

/// Captured live from `POST /api/assets/force-accept` with a
/// METADATA_READY id — a deliberate no-op refusal (no mutation).
const String kForceAcceptJson = r'''
{"items":[{"record_id":"0b91ca23-c3ed-4312-a4fc-74cd0033a240","accepted":false,
"previous_stage":"METADATA_READY","new_stage":null,"score":0.9100000000000001,
"reason":"Already accepted (metadata is ready)."}],"accepted":0,"refused":1}
''';

/// Captured live from `POST /api/assets/rename-suggest` (dry run).
const String kRenameSuggestJson = r'''
{"items":[{"record_id":"0b91ca23-c3ed-4312-a4fc-74cd0033a240",
"filename":"Wire_loop_trimming_tool_2K_20261013092634.jpg",
"download_name":"sculpting-tool-with-wooden-handle-and-wire-loop.jpg",
"changed":false,"error":null}],"updated":1,"failed":0}
''';

/// Captured live from `POST /api/assets/rename` with an unknown id.
const String kRenameNotFoundJson = r'''
{"items":[{"record_id":"ffffffff-0000-0000-0000-000000000000","filename":"",
"download_name":null,"changed":false,"error":"Record not found."}],
"updated":0,"failed":1}
''';

/// Captured live from `POST /api/assets/apply-suggested-names` (unknown id).
const String kApplyEmptyJson = '{"items":[],"updated":0,"failed":0}';

/// Live error sentence from `POST /api/assets/csv` with an id that has no
/// exportable row (409).
const String kCsvEmptyDetail =
    'No exportable rows. Generate metadata for at least one image before exporting.';

/// Live error sentence from `POST /api/assets/bundle` with no selection.
const String kBundleEmptyDetail =
    'record_ids must not be empty — a bundle needs an explicit selection.';

class _Request {
  _Request(this.method, this.body);

  final String method;
  final Object? body;
}

/// Real Dio + a routed adapter: fixtures flow through the actual Dio stack
/// (transformer, error shaping), so both parsing *and* `mapDioError`
/// behaviour are exercised exactly as in production.
class _FixtureAdapter implements HttpClientAdapter {
  final Map<String, Object?> jsonByPath = <String, Object?>{};
  final Map<String, ({int status, String detail})> errors =
      <String, ({int status, String detail})>{};
  final Map<String, ({Uint8List bytes, Map<String, List<String>> headers})>
      binaries = <String, ({Uint8List bytes, Map<String, List<String>> headers})>{};
  final List<_Request> requests = <_Request>[];

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    final String path = options.uri.path;
    requests.add(_Request(options.method, _decode(options.data)));

    final ({int status, String detail})? error = errors[path];
    if (error != null) {
      return ResponseBody.fromString(
        jsonEncode(<String, Object?>{'detail': error.detail}),
        error.status,
        headers: <String, List<String>>{
          Headers.contentTypeHeader: <String>[Headers.jsonContentType],
        },
      );
    }

    final ({Uint8List bytes, Map<String, List<String>> headers})? binary =
        binaries[path];
    if (binary != null) {
      return ResponseBody.fromBytes(
        binary.bytes,
        200,
        headers: <String, List<String>>{
          Headers.contentTypeHeader: <String>['application/octet-stream'],
          ...binary.headers,
        },
      );
    }

    return ResponseBody.fromString(
      jsonEncode(jsonByPath[path] ?? 'no fixture for $path'),
      200,
      headers: <String, List<String>>{
        Headers.contentTypeHeader: <String>[Headers.jsonContentType],
      },
    );
  }

  Object? _decode(Object? data) {
    if (data is String) {
      try {
        return jsonDecode(data);
      } on FormatException {
        return data;
      }
    }
    return data;
  }

  @override
  void close({bool force = false}) {}
}

void main() {
  late _FixtureAdapter adapter;
  late DeliveryRepository repo;

  setUp(() {
    adapter = _FixtureAdapter()
      ..jsonByPath['/api/records'] = jsonDecode(kCandidatesJson)
      ..jsonByPath['/api/assets/csv/preview'] = jsonDecode(kPreviewJson)
      ..jsonByPath['/api/assets/force-accept'] = jsonDecode(kForceAcceptJson)
      ..jsonByPath['/api/assets/rename-suggest'] = jsonDecode(kRenameSuggestJson)
      ..jsonByPath['/api/assets/rename'] = jsonDecode(kRenameNotFoundJson)
      ..jsonByPath['/api/assets/apply-suggested-names'] =
          jsonDecode(kApplyEmptyJson)
      ..binaries['/api/assets/csv'] = (
        bytes: Uint8List.fromList(utf8.encode('Filename,Title\r\na,b\r\n')),
        headers: <String, List<String>>{
          'content-disposition': <String>[
            'attachment; filename="adobe-stock-metadata.csv"',
          ],
          'x-csv-row-count': <String>['1'],
        },
      )
      ..binaries['/api/assets/bundle'] = (
        bytes: Uint8List.fromList(<int>[0x50, 0x4b, 0x03, 0x04]),
        headers: <String, List<String>>{
          'content-disposition': <String>[
            'attachment; filename="adobe-stock-delivery.zip"',
          ],
          'content-type': <String>['application/zip'],
        },
      );
    repo = DeliveryRepositoryImpl(Dio()..httpClientAdapter = adapter);
  });

  group('candidates parse the captured records payload', () {
    test('full row + trimmed row, effective name falls back safely',
        () async {
      final List<DeliveryCandidate> rows = await repo.fetchCandidates('adobe_stock');

      expect(rows, hasLength(2));
      expect(rows[0].id, '0b91ca23-c3ed-4312-a4fc-74cd0033a240');
      expect(rows[0].effectiveName, 'sculpting-tool-with-wooden-handle-and-wire-loop.jpg');
      expect(rows[0].title, 'Sculpting tool with wooden handle and wire loop');
      expect(rows[0].isUsed, isTrue);
      expect(rows[0].deliverable, isTrue);
      expect(rows[0].forceable, isFalse); // METADATA_READY cannot be forced

      // Defensive parse: missing upload_filename/title → filename fallback.
      expect(rows[1].uploadFilename, isNull);
      expect(rows[1].effectiveName, 'Acoustic_guitar_bridge_pins_arrangement_2K_20261013092129.jpg');
      expect(rows[1].title, isNull);
      expect(rows[1].isUsed, isFalse);
    });

    test('wrong container throws ServerException instead of fake rows',
        () async {
      adapter.jsonByPath['/api/records'] = '<html>proxy error</html>';
      expect(
        () => repo.fetchCandidates('adobe_stock'),
        throwsA(isA<ServerException>()),
      );
    });

    test('state-bearing rows gate deliverable on the state contract', () async {
      adapter.jsonByPath['/api/records'] = jsonDecode(
        '{"items":['
        '{"id":"a","filename":"a.jpg","stage":"COLLECTED",'
        '"state":"READY_TO_PUBLISH"},'
        '{"id":"b","filename":"b.jpg","stage":"METADATA_READY",'
        '"state":"COLLECTED"},'
        '{"id":"c","filename":"c.jpg","stage":"METADATA_READY",'
        '"state":"PUBLISHED"}],'
        '"total":3}',
      );

      final List<DeliveryCandidate> rows =
          await repo.fetchCandidates('adobe_stock');

      expect(rows, hasLength(3));
      // `state` wins over the stage pair once the backend ships it…
      expect(rows[0].deliverable, isTrue);
      expect(rows[1].deliverable, isFalse);
      expect(rows[2].deliverable, isTrue);
      // …and the raw stage text still rides along for the Process column.
      expect(rows[1].stage, 'METADATA_READY');
      expect(rows[1].state, 'COLLECTED');
    });
  });

  group('csv preview parses captured JSON', () {
    test('deliverable-set payload: rows, lines, empty notes', () async {
      final CsvPreview preview = await repo.previewCsv('adobe_stock');

      expect(preview.rowCount, 142);
      expect(preview.warnings, isEmpty);
      expect(preview.skipped, isEmpty);
      expect(preview.lines.first, 'Filename,Title,Keywords,Category,Releases');
      expect(preview.lines, hasLength(3));
      expect(preview.lines[1], startsWith('vintage-cast-iron-hand-coffee-grinder'));
    });

    test('warnings payload: both live notes surface', () async {
      adapter.jsonByPath['/api/assets/csv/preview'] =
          jsonDecode(kPreviewWarningsJson);

      final CsvPreview preview = await repo.previewCsv(
        'adobe_stock',
        recordIds: <String>['a', 'b'],
      );

      expect(preview.rowCount, 2);
      expect(preview.warnings, hasLength(2));
      expect(preview.warnings.first, contains('no generated title'));
    });

    test('request body: no selection → only_ready true; selection → false',
        () async {
      await repo.previewCsv('adobe_stock');
      await repo.previewCsv('adobe_stock', recordIds: <String>['a']);

      expect(
        adapter.requests.map<Object?>(( _Request r) => r.body).toList(),
        <Object?>[
          <String, Object?>{'record_ids': null, 'only_ready': true},
          <String, Object?>{'record_ids': <String>['a'], 'only_ready': false},
        ],
      );
    });
  });

  group('downloads carry the live Content-Disposition filenames', () {
    test('csv export → adobe-stock-metadata.csv', () async {
      final DeliveryFile file = await repo.exportCsv('adobe_stock');

      expect(file.fileName, 'adobe-stock-metadata.csv');
      expect(utf8.decode(file.bytes), contains('Filename,Title'));
      expect(
        adapter.requests.single.body,
        <String, Object?>{'record_ids': null, 'only_ready': true},
      );
    });

    test('bundle → adobe-stock-delivery.zip, explicit selection', () async {
      final DeliveryFile file = await repo.bundleZip(
        'adobe_stock',
        recordIds: <String>['r1', 'r2'],
      );

      expect(file.fileName, 'adobe-stock-delivery.zip');
      expect(file.bytes, <int>[0x50, 0x4b, 0x03, 0x04]);
      expect(
        adapter.requests.single.body,
        <String, Object?>{
          'record_ids': <String>['r1', 'r2'],
          'only_ready': false,
        },
      );
    });
  });

  group('force-accept parses the captured refusal', () {
    test('counts + per-item reason/score', () async {
      final ForceAcceptOutcome outcome = await repo.forceAccept(
        'adobe_stock',
        recordIds: <String>['0b91ca23-c3ed-4312-a4fc-74cd0033a240'],
        reason: 'delivery smoke test',
      );

      expect(outcome.accepted, 0);
      expect(outcome.refused, 1);
      expect(outcome.items, hasLength(1));
      expect(outcome.items.single.accepted, isFalse);
      expect(outcome.items.single.previousStage, 'METADATA_READY');
      expect(outcome.items.single.newStage, isNull);
      expect(outcome.items.single.score, closeTo(0.91, 0.001));
      expect(outcome.items.single.reason, 'Already accepted (metadata is ready).');
    });

    test('400 with empty selection maps to ValidationException detail',
        () async {
      adapter.errors['/api/assets/force-accept'] = (
        status: 400,
        detail: 'record_ids must not be empty.',
      );

      expect(
        () => repo.forceAccept(
          'adobe_stock',
          recordIds: <String>[],
          reason: 'x',
        ),
        throwsA(
          isA<ValidationException>().having(
            (ValidationException e) => e.message,
            'message',
            'record_ids must not be empty.',
          ),
        ),
      );
    });
  });

  group('rename endpoints parse captured responses', () {
    test('rename-suggest → updated row with suggested name', () async {
      final RenameOutcome outcome = await repo.suggestNames(
        'adobe_stock',
        items: <RenameEntry>[const RenameEntry(recordId: 'r1', name: '')],
        regenerate: true,
      );

      expect(outcome.updated, 1);
      expect(outcome.failed, 0);
      expect(outcome.items.single.downloadName,
          'sculpting-tool-with-wooden-handle-and-wire-loop.jpg');
      expect(outcome.items.single.changed, isFalse);
      expect(outcome.items.single.error, isNull);
    });

    test('rename of an unknown id → per-row error, failed count', () async {
      final RenameOutcome outcome = await repo.rename(
        'adobe_stock',
        items: <RenameEntry>[
          const RenameEntry(recordId: 'ffffffff-0000-0000-0000-000000000000',
              name: 'brand-new-name'),
        ],
      );

      expect(outcome.updated, 0);
      expect(outcome.failed, 1);
      expect(outcome.items.single.error, 'Record not found.');
      expect(outcome.items.single.downloadName, isNull);
    });

    test('apply-suggested-names with no matches → empty outcome', () async {
      final RenameOutcome outcome = await repo.applySuggestedNames(
        'adobe_stock',
        items: <RenameEntry>[
          const RenameEntry(recordId: 'ffffffff-0000-0000-0000-000000000000',
              name: ''),
        ],
      );

      expect(outcome.items, isEmpty);
      expect(outcome.updated, 0);
      expect(outcome.failed, 0);
    });
  });

  group('error mapping keeps the server sentences', () {
    test('byte endpoint 409 detail survives the raw-bytes error body',
        () async {
      adapter.errors['/api/assets/csv'] = (status: 409, detail: kCsvEmptyDetail);

      expect(
        () => repo.exportCsv('adobe_stock'),
        throwsA(
          isA<ServerException>()
              .having((ServerException e) => e.message, 'message', kCsvEmptyDetail),
        ),
      );
    });

    test('bundle 400 detail maps to ValidationException', () async {
      adapter.errors['/api/assets/bundle'] = (
        status: 400,
        detail: kBundleEmptyDetail,
      );

      expect(
        () => repo.bundleZip('adobe_stock', recordIds: <String>[]),
        throwsA(
          isA<ValidationException>().having(
            (ValidationException e) => e.message,
            'message',
            kBundleEmptyDetail,
          ),
        ),
      );
    });
  });
}
