import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

import 'package:ai_stock_studio/core/utils/app_exception.dart';
import 'package:ai_stock_studio/features/auth/data/auth_repository_impl.dart';
import 'package:ai_stock_studio/features/auth/domain/auth_repository.dart';

class MockDio extends Mock implements Dio {}

void main() {
  late MockDio dio;
  late AuthRepository repo;

  RequestOptions opts(String path) => RequestOptions(path: path);

  DioException badResponse(int status, {Object? data}) => DioException(
        requestOptions: opts('/api/auth/login'),
        response: Response<dynamic>(
          requestOptions: opts('/api/auth/login'),
          statusCode: status,
          data: data,
        ),
        type: DioExceptionType.badResponse,
        message: 'HTTP $status',
      );

  DioException connectionBroken() => DioException(
        requestOptions: opts('/api/auth/login'),
        type: DioExceptionType.connectionError,
        message: 'connection refused',
        error: 'connection refused',
      );

  setUp(() {
    dio = MockDio();
    repo = AuthRepositoryImpl(dio);
  });

  group('DioException → AppException mapping table', () {
    final Map<String, (DioException, Matcher Function())> table =
        <String, (DioException, Matcher Function())>{
      'connectionError → NetworkException': (
        connectionBroken(),
        () => isA<NetworkException>(),
      ),
      '401 → AuthException': (
        badResponse(401, data: <String, Object>{'detail': 'Invalid credentials'}),
        () => isA<AuthException>(),
      ),
      '404 → NotFoundException': (
        badResponse(404),
        () => isA<NotFoundException>(),
      ),
      '422 → ValidationException': (
        badResponse(422),
        () => isA<ValidationException>(),
      ),
      '500 → ServerException': (badResponse(500), () => isA<ServerException>()),
    };

    table.forEach((name, entry) {
      test('login surfaces $name', () async {
        when(
          () => dio.post('/api/auth/login', data: any(named: 'data')),
        ).thenThrow(entry.$1);

        await expectLater(
          repo.login('admin', 'wrong'),
          throwsA(entry.$2()),
        );
      });
    });
  });

  test('login posts {username, password} to /api/auth/login', () async {
    when(() => dio.post('/api/auth/login', data: any(named: 'data')))
        .thenAnswer(
      (_) async => Response<dynamic>(
        requestOptions: opts('/api/auth/login'),
        statusCode: 200,
        data: <String, Object>{
          'user': <String, Object>{'username': 'admin'},
        },
      ),
    );

    await repo.login('admin', 'secret');

    final VerificationResult result = verify(
      () => dio.post('/api/auth/login', data: captureAny(named: 'data')),
    );
    expect(result.callCount, 1);
    expect(result.captured.single, <String, Object>{
      'username': 'admin',
      'password': 'secret',
    });
  });

  test('sessionAlive is true on 200', () async {
    when(() => dio.get('/api/auth/me')).thenAnswer(
      (_) async => Response<dynamic>(
        requestOptions: opts('/api/auth/me'),
        statusCode: 200,
        data: <String, Object>{
          'user': <String, Object>{'username': 'admin'},
        },
      ),
    );

    expect(await repo.sessionAlive(), isTrue);
  });

  test('sessionAlive is false on 401', () async {
    when(() => dio.get('/api/auth/me')).thenThrow(
      badResponse(401, data: <String, Object>{'detail': 'Not authenticated'}),
    );

    expect(await repo.sessionAlive(), isFalse);
  });

  test('sessionAlive maps 500 to ServerException', () async {
    when(() => dio.get('/api/auth/me')).thenThrow(badResponse(500));

    await expectLater(repo.sessionAlive(), throwsA(isA<ServerException>()));
  });

  test('logout completes even when the endpoint errors', () async {
    when(() => dio.post('/api/auth/logout')).thenThrow(badResponse(500));

    await repo.logout(); // must not throw — teardown is best-effort
    verify(() => dio.post('/api/auth/logout')).called(1);
  });
}
