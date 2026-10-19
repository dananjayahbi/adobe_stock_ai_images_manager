import 'package:ai_stock_studio/core/utils/platform_paths.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('platformPath', () {
    test('adobe_stock keeps the legacy top-level routes', () {
      expect(platformPath('adobe_stock', 'records'), '/api/records');
      expect(platformPath('adobe_stock', '/records'), '/api/records');
      expect(
        platformPath('adobe_stock', 'records/2/file'),
        '/api/records/2/file',
      );
    });

    test('other platforms use scoped routes', () {
      expect(platformPath('freepik', 'records'), '/api/platforms/freepik/records');
      expect(platformPath('freepik', '/records'), '/api/platforms/freepik/records');
      expect(
        platformPath('freepik', '/records/7'),
        '/api/platforms/freepik/records/7',
      );
    });

    test('query strings survive untouched', () {
      expect(
        platformPath('adobe_stock', 'records?limit=8'),
        '/api/records?limit=8',
      );
      expect(
        platformPath('adobe_stock', '/records?limit=8'),
        '/api/records?limit=8',
      );
      expect(
        platformPath('freepik', '/records?limit=8'),
        '/api/platforms/freepik/records?limit=8',
      );
    });

    test('never produces // in the path portion', () {
      for (final String rest in <String>['', 'records', '/records', '//records']) {
        final String legacy = platformPath('adobe_stock', rest);
        expect(legacy.split('?').first.contains('//'), isFalse,
            reason: legacy);
        final String scoped = platformPath('freepik', rest);
        expect(scoped.split('?').first.contains('//'), isFalse,
            reason: scoped);
      }
    });
  });

  group('thumbnailsUrl', () {
    test('basename from an absolute Windows path', () {
      expect(
        thumbnailsUrl(
          'http://localhost:8001',
          r'E:\storage\platforms\adobe_stock\thumbs\a.jpg',
        ),
        'http://localhost:8001/thumbnails/a.jpg',
      );
    });

    test('basename from an absolute POSIX path', () {
      expect(
        thumbnailsUrl(
          'http://192.168.1.23:8001',
          '/var/data/platforms/adobe_stock/thumbs/b.png',
        ),
        'http://192.168.1.23:8001/thumbnails/b.png',
      );
    });

    test('bare basename and trailing-slash base URL', () {
      expect(
        thumbnailsUrl('http://localhost:8001/', 'c.jpg'),
        'http://localhost:8001/thumbnails/c.jpg',
      );
      expect(
        thumbnailsUrl('https://studio.trycloudflare.com', 'd.jpg'),
        'https://studio.trycloudflare.com/thumbnails/d.jpg',
      );
    });

    test('a URL input still reduces to its filename', () {
      expect(
        thumbnailsUrl(
          'http://localhost:8001',
          'http://host/thumbnails/e.png',
        ),
        'http://localhost:8001/thumbnails/e.png',
      );
    });
  });
}
