# 03 — Flutter Architecture: "AI Stock Studio" Mobile

**Status:** implementation-ready spec · **Author:** planning agent C · **Verified against pub.dev:** 2026-10-15

Scope: a Flutter app at repo-root `mobile/` that talks **directly** to the FastAPI
backend (default `http://localhost:8007`, configurable to LAN IP / Cloudflare tunnel):
pick a platform, review gallery images, run/monitor pipelines and delivery jobs.
The **platform-isolation rule from `ARCHITECTURE.md` applies to the app too** —
no API call may resolve another platform's data, and no mutable UI state may be
shared across platform scopes.

Grounded backend facts: `GET /health` → `{"status":"ok"}` (unauthenticated);
`POST /api/auth/login {username,password}` sets HttpOnly `studio_session` via
`Set-Cookie`; `GET /api/auth/me` validates; `POST /api/auth/logout` always 200;
catalogue `GET /api/platforms`; legacy Adobe routes at top level (`/api/records`,
`/api/queues/...`), future scoped routers `/api/platforms/{id}/...`; SSE is
`text/event-stream` with `data:` frames + terminal `event: done`; thumbnails at
`/thumbnails/<file>` with `no-cache`.

---

## 1. Technology decisions (all versions verified on pub.dev, 2026-10-15)

| Concern | Choice | Version | Rationale |
|---|---|---|---|
| Framework | Flutter, **stable channel** | ≥ 3.47.x | Current stable is 3.47.7 (Dart 3.13.5, 2026-10-08). Pin `sdk: ^3.13.0` in `pubspec.yaml`; all picks below resolve on it. |
| State mgmt | `flutter_riverpod` | 3.4.3 | Compile-safe DI + `AsyncValue` (loading/error for free), provider `.family` gives us **per-platform state keys for free** (§3.5). Bloc = more boilerplate for the same wiring; GetX mixes DI/UI/routing and fights the layering below; Provider lacks async ergonomics. |
| Navigation | `go_router` | 18.1.0 | Declarative routes with a single `redirect` driven by auth state (`refreshListenable`) — the web app's login-gate pattern translated to Dart. |
| Networking | `dio` + `dio_cookie_manager` + `cookie_jar` | 5.11.1 / 3.5.0 / 4.0.9 | Dio gives interceptors (base-URL rewrite, auth, logging) and **streamed responses** needed for SSE. `dio_cookie_manager` is the current separate cookie plugin (no longer inside dio); `cookie_jar` supplies the `CookieJar` interface we implement securely. |
| Secure storage | `flutter_secure_storage` | 11.2.0 | Keychain/Keystore-backed. Holds the `studio_session` cookie value — a bearer credential must not sit in plaintext prefs. |
| Images | `cached_network_image` | 4.0.4 | Disk-cached grid thumbnails; matters over slow tunnels. Pair with `ImageCache` sizing for large galleries. |
| SSE | **Dio `ResponseType.stream` + tiny local parser** | (dio only) | Verified: package `sse` 4.2.0 is explicitly *not* general-purpose — it's a bidirectional protocol requiring a paired `sse` server, which FastAPI's plain `StreamingResponse` is not. Dio streaming reuses the cookie interceptor + logging and needs ~30 lines of frame parsing. |
| Fonts | `google_fonts` | 9.0.0 | Matches the web brand typography; requires Flutter ≥ 3.47 (why the channel pin above). Bundle the 2–3 used families as assets for offline builds (runtime HTTP fetch fails on planes/tunnels). |
| Icons | `lucide_flutter` | 1.47.0 | **Chosen over `phosphor_flutter` (2.1.0 exists):** the web frontend already ships `lucide-react ^0.330.0`, so mobile gets icon parity with the brand for free. |
| Offline/local DB | **none for MVP** | — | Server is the source of truth; lists are always fetched fresh (also the *safest* isolation posture — no local DB to partition per platform). Image bytes are cached by `cached_network_image`. Small KV (connection profiles, active profile id) goes in `shared_preferences` 2.5.6. Rejected: `isar` 3.1.0+1 declares `sdk >=2.17.0 <3.0.0` — **incompatible with Dart 3**; `hive_ce` 2.22.0 works but earns its complexity only if offline drafts become a real requirement. |
| Lints | `flutter_lints` | 6.0.0 | Baseline + a handful of local rules (§5). |
| Test/mock | `mocktail`, `integration_test` | 1.0.5, SDK | Codegen-free mocks; SDK integration harness. |

`pubspec.yaml` pin (illustrative):

```yaml
environment:
  sdk: ^3.13.0        # Flutter stable >= 3.47.x
dependencies:
  flutter_riverpod: ^3.4.3
  go_router: ^18.1.0
  dio: ^5.11.1
  dio_cookie_manager: ^3.5.0
  cookie_jar: ^4.0.9
  flutter_secure_storage: ^11.2.0
  cached_network_image: ^4.0.4
  google_fonts: ^9.0.0
  lucide_flutter: ^1.47.0
  shared_preferences: ^2.5.6
```

---

## 2. Feature-first folder tree (`mobile/`)

```text
mobile/
├── pubspec.yaml
├── analysis_options.yaml
├── lib/
│   ├── main.dart                        # runApp(ProviderScope(child: App()))
│   ├── app/
│   │   ├── bootstrap.dart               # async init: prefs, secure store, profile, dio
│   │   ├── router.dart                  # GoRouter + auth redirect
│   │   ├── lifecycle_observer.dart      # resume/pause hooks (§4)
│   │   └── theme/                       # ← design tokens land here (design doc owns content)
│   │       ├── theme.dart               # ThemeData assembly
│   │       ├── tokens.dart              # colors/spacing/radii (ported from web brand)
│   │       └── typography.dart          # google_fonts text themes
│   ├── core/
│   │   ├── config/
│   │   │   ├── app_config.dart          # env, default base URL, timeouts
│   │   │   └── env.dart                 # APP_ENV dev|prod (dart-define)
│   │   ├── network/
│   │   │   ├── dio_factory.dart         # builds Dio w/ interceptors
│   │   │   ├── base_url_interceptor.dart# injects active profile base URL
│   │   │   ├── auth_interceptor.dart    # 401 → forced logout
│   │   │   ├── auth_cookie_jar.dart     # SecureCookieJar (studio_session)
│   │   │   ├── api_logger.dart          # dio LogInterceptor, kDebugMode only
│   │   │   └── sse_parser.dart          # text/event-stream frame parser
│   │   ├── storage/
│   │   │   ├── secure_store.dart        # flutter_secure_storage wrapper
│   │   │   └── prefs_store.dart         # shared_preferences wrapper (KV only)
│   │   ├── utils/
│   │   │   ├── platform_paths.dart      # platformId → URL path resolver (§3.5)
│   │   │   ├── app_exception.dart       # sealed exception hierarchy (§4)
│   │   │   ├── ui_message.dart          # exception → user-facing string
│   │   │   └── formatters.dart          # dates, counts, bytes
│   │   └── widgets/
│   │       ├── async_view.dart          # AsyncValue → loading/error/data
│   │       ├── empty_state.dart
│   │       ├── error_view.dart          # retry affordance
│   │       └── thumbnail.dart           # cached_network_image w/ no-cache thumb URL
│   ├── features/
│   │   ├── auth/
│   │   │   ├── data/
│   │   │   │   ├── auth_api.dart
│   │   │   │   └── auth_repository_impl.dart
│   │   │   ├── domain/
│   │   │   │   ├── auth_repository.dart     # interface
│   │   │   │   └── user_session.dart        # entity
│   │   │   └── presentation/
│   │   │       ├── login_screen.dart
│   │   │       ├── login_form.dart
│   │   │       └── auth_controller.dart     # AsyncNotifier<AuthStatus>
│   │   ├── platforms/                       # hub / picker
│   │   │   ├── data/
│   │   │   │   ├── platform_api.dart
│   │   │   │   └── platform_repository_impl.dart
│   │   │   ├── domain/
│   │   │   │   ├── platform.dart            # id, name, tagline, status
│   │   │   │   └── platform_repository.dart
│   │   │   └── presentation/
│   │   │       ├── platform_hub_screen.dart
│   │   │       ├── platform_card.dart
│   │   │       └── platforms_controller.dart
│   │   ├── dashboard/
│   │   │   ├── data/
│   │   │   │   ├── dashboard_api.dart
│   │   │   │   └── dashboard_repository_impl.dart
│   │   │   ├── domain/
│   │   │   │   ├── dashboard_stats.dart
│   │   │   │   └── dashboard_repository.dart
│   │   │   └── presentation/
│   │   │       ├── dashboard_screen.dart
│   │   │       ├── stat_tile.dart
│   │   │       └── dashboard_controller.dart
│   │   ├── gallery/
│   │   │   ├── data/
│   │   │   │   ├── record_dto.dart          # API JSON → toEntity()
│   │   │   │   ├── gallery_api.dart
│   │   │   │   └── gallery_repository_impl.dart
│   │   │   ├── domain/
│   │   │   │   ├── record.dart              # entity
│   │   │   │   ├── gallery_query.dart       # page, filters, sort
│   │   │   │   └── gallery_repository.dart
│   │   │   └── presentation/
│   │   │       ├── gallery_screen.dart
│   │   │       ├── gallery_grid.dart
│   │   │       ├── record_card.dart
│   │   │       ├── gallery_filter_bar.dart
│   │   │       └── gallery_controller.dart  # family by platformId + query
│   │   ├── process/                         # queues + pipeline/SSE monitor
│   │   │   ├── data/
│   │   │   │   ├── process_api.dart
│   │   │   │   ├── process_stream.dart      # dio stream → Stream<ProcessEvent>
│   │   │   │   └── process_repository_impl.dart
│   │   │   ├── domain/
│   │   │   │   ├── queue_summary.dart
│   │   │   │   ├── process_event.dart       # parsed SSE payload
│   │   │   │   └── process_repository.dart
│   │   │   └── presentation/
│   │   │       ├── process_screen.dart
│   │   │       ├── queue_tile.dart
│   │   │       └── process_controller.dart  # Stream watcher, family by platformId
│   │   ├── delivery/
│   │   │   ├── data/
│   │   │   │   ├── delivery_api.dart
│   │   │   │   └── delivery_repository_impl.dart
│   │   │   ├── domain/
│   │   │   │   ├── delivery_job.dart        # csv / bundle / rename requests
│   │   │   │   └── delivery_repository.dart
│   │   │   └── presentation/
│   │   │       ├── delivery_screen.dart
│   │   │       ├── csv_sheet.dart
│   │   │       └── delivery_controller.dart
│   │   └── settings/                        # connection profiles + account
│   │       ├── data/
│   │       │   ├── profile_store.dart       # shared_preferences JSON
│   │       │   ├── health_api.dart          # GET /health, GET /api/auth/me
│   │       │   └── settings_repository_impl.dart
│   │       ├── domain/
│   │       │   ├── connection_profile.dart  # id, label, baseUrl, health
│   │       │   └── settings_repository.dart
│   │       └── presentation/
│   │           ├── settings_screen.dart
│   │           ├── connection_editor_sheet.dart
│   │           └── settings_controller.dart
├── test/                                   # mirrors lib/ 1:1 (unit, widget, golden/)
└── integration_test/
    ├── mock_backend.dart                   # loopback HttpServer, canned JSON + SSE
    └── app_flow_test.dart                  # login → hub → gallery → process
```

Pragmatism: `domain/` holds an entity, a repository **interface**, and a small model
only where logic exists (`gallery_query`, `delivery_job`). No usecase classes for
pass-through API calls — controllers call repositories directly; add a usecase only
when two repositories must be orchestrated.

---

## 3. Layer contracts

> **Screen files:** the tree above shows the *core* screen per feature. The
> additional screens required by [05](./05-screen-inventory.md) — splash,
> gallery detail, batch detail, coming-soon, error/offline, connections
> (+edit), account, about — are **additive** files under the owning feature's
> `presentation/` (e.g. `features/gallery/presentation/gallery_detail_screen.dart`,
> `features/auth/presentation/splash_screen.dart`, `features/settings/presentation/…`).
> **05 is authoritative for screen→file names.**

```mermaid
flowchart TB
    subgraph P["Presentation (features/*/presentation)"]
        S[Screens / widgets] --> C[Controllers - AsyncNotifier / StreamNotifier]
    end
    subgraph D["Domain (features/*/domain)"]
        E[Entities] RI[Repository interfaces]
    end
    subgraph DA["Data (features/*/data)"]
        API[API DTOs] DS[DataSources - dio] RIImpl[Repository impls]
        RIImpl --> DS
        DS --> API
        RIImpl --> RI
        API -->|toEntity()| E
    end
    subgraph CO["Core (cross-cutting)"]
        NW[Dio + interceptors + SecureCookieJar + SSE parser]
        ST[secure / prefs stores]
        CFG[AppConfig + ConnectionProfile]
        PP[platform_paths resolver]
    end
    C --> RI
    DS --> NW
    NW --> CFG
    DS --> PP
    BE[(FastAPI backend<br/>:8007)] <--HTTP/SSE--> NW
```

Dependency rule: presentation → domain ← data; only `core/` is imported by all
layers. Nothing in `domain/` imports dio/Flutter widgets.

### 3.1 API model → domain entity

DTOs own JSON; entities own the app. Every datasource returns entities —
`fromJson`/`toEntity` never leak above `data/`:

```dart
class RecordDto {
  const RecordDto(this.id, this.title, this.thumbFile, this.status);
  final int id; final String? title; final String? thumbFile; final String status;

  factory RecordDto.fromJson(Map<String, dynamic> j) => RecordDto(
      j['id'] as int, j['title'] as String?, j['thumb_file'] as String?,
      j['status'] as String? ?? 'unknown');

  Record toEntity() => Record(
      id: id, title: title, status: status,
      thumbUrl: thumbFile == null ? null : '/thumbnails/$thumbFile');
}
```

Field names must be re-checked against `backend/schemas.py` at implementation time;
DTO tests pin the contract (`record_dto_test.dart` uses real captured JSON).

### 3.2 Connection profiles (base URL injection)

`ConnectionProfile { id, label, baseUrl, lastStatus, lastCheckedAt }` — named,
persisted as JSON in `shared_preferences` (`profiles_v1`, `active_profile_v1`).
Built-ins seeded: **Local** (`http://localhost:8007`), plus a hint that Android
emulator loopback is `10.0.2.2`. Health check: `GET {baseUrl}/health` →
`{"status":"ok"}` (no auth required). Session validity check: `GET /api/auth/me`.

Injection happens per-request so switching is instant — no Dio rebuild:

```dart
class BaseUrlInterceptor extends Interceptor {
  BaseUrlInterceptor(this.current);
  final ConnectionProfile Function() current;   // reads active profile provider

  @override
  void onRequest(RequestOptions o, RequestInterceptorHandler h) {
    o.baseUrl = current().baseUrl;              // rewritten on every call
    h.next(o);
  }
}
```

Switching profiles: update `activeProfileProvider` → `ref.invalidate` feature
providers + `healthProvider` → router stays put if the new profile answers `/health`
and `/api/auth/me`; otherwise the auth redirect fires naturally.

### 3.3 Auth cookie: capture → store → replay

1. `POST /api/auth/login` — dio follows the response; `CookieManager` intercepts
   `Set-Cookie: studio_session=…` and delegates to our jar.
2. `SecureCookieJar` (implements `cookie_jar`'s `CookieJar`) persists the raw
   `Set-Cookie` value in `flutter_secure_storage` (encrypted; a file-based
   `PersistCookieJar` would leave a plaintext bearer token on disk). The key is
   **profile-scoped** (`studio_session_cookie:<profileId>`) and the app holds one
   jar per connection profile, swapped on profile switch — LAN and tunnel
   sessions must never cross (06 §5).
3. Every later request: `CookieManager.loadForRequest()` → jar → `Cookie` header
   replayed automatically, including on SSE requests.

```dart
class SecureCookieJar implements CookieJar {
  SecureCookieJar(this._storage, this._profileId);
  final FlutterSecureStorage _storage;
  final String _profileId; // one jar per connection profile — see 06 §5
  String get _key => 'studio_session_cookie:$_profileId';

  @override
  Future<void> saveFromResponse(Uri uri, List<Cookie> cs) async {
    final c = cs.where((c) => c.name == 'studio_session').firstOrNull;
    if (c == null) return;
    await _storage.write(key: _key, value: c.toString());
  }

  @override
  Future<List<Cookie>> loadForRequest(Uri uri) async {
    final raw = await _storage.read(key: _key);
    return raw == null ? const [] : [Cookie.fromSetCookieHeaderValue(raw)];
  }
}
```

### 3.4 401 → forced logout

One interceptor, mirroring `frontend-new/src/lib/client.ts`:

```dart
class AuthInterceptor extends Interceptor {
  AuthInterceptor(this._ref);
  final Ref _ref;

  @override
  void onError(DioException e, ErrorInterceptorHandler h) async {
    final path = e.requestOptions.path;
    if (e.response?.statusCode == 401 && !path.endsWith('/api/auth/login')) {
      await _ref.read(authControllerProvider.notifier).forceLogout();
      // forceLogout: best-effort POST /api/auth/logout, clear jar,
      // set AuthStatus.loggedOut → router redirect to /login
    }
    h.next(e);
  }
}
```

`forceLogout` is idempotent and never throws (the backend may be what's down).
Login's own 401 surfaces as a form error, not a redirect — no redirect loop.

### 3.5 Per-platform scoping (no data leaks)

`platformId` travels **in the URL path**, exactly like the backend contract.
All path building goes through one resolver — feature code never string-concats
platform URLs:

```dart
/// Legacy Adobe routes are top-level today; scoped routers land under
/// /api/platforms/{id}/... (ARCHITECTURE.md §6). One switch, one day of work.
String platformPath(String platformId, String rest) =>
    platformId == 'adobe_stock' ? '/api/$rest' : '/api/platforms/$platformId/$rest';

// gallery_api.dart
Future<RecordListDto> page(String pid, GalleryQuery q) async {
  final r = await _dio.get(platformPath(pid, 'records'), queryParameters: q.toMap());
  ...
}
```

State isolation is enforced by Riverpod: every platform-scoped provider is a
**`.family` keyed by `platformId`** (`galleryControllerProvider('adobe_stock')` ≠
`galleryControllerProvider('freepik')`), and route paths carry the id
(`/p/:platformId/gallery`). Rules:

- Controllers validate that their `platformId` matches the route's before rendering.
- Switching platforms **invalidates** (`ref.invalidate` on the old key) the previous
  platform's controllers after a grace period — stale widgets of platform A can
  never render platform B data, and memory doesn't accumulate.
- Thumbnail URLs are absolute (`{baseUrl}/thumbnails/…`) and therefore inherently
  scoped to whatever backend the profile points at.
- The catalogue itself (`GET /api/platforms`) is the only cross-platform endpoint
  (it returns metadata, never data).

---

## 4. Cross-cutting conventions

- **Error handling — exceptions (one convention).** Datasources throw; repositories
  map `DioException` → `AppException` via one `mapDioError()` helper so **no
  `DioException` ever escapes `data/`**. Sealed hierarchy (`core/utils/app_exception.dart`):
  `NetworkException`, `ApiException(status, detail)` (backend `detail` verbatim, like
  the web client), `AuthException`, `NotFoundException`. Controllers expose
  `AsyncValue`, which already *is* a result type — a hand-rolled `Result<T>` would
  double-wrap it. UI maps exceptions to copy via `uiMessage.dart`.
- **Logging:** dio's built-in `LogInterceptor` registered in `dio_factory.dart`
  **only when `kDebugMode`** (`core/network/api_logger.dart`); zero extra dependency.
  Never log cookies or credentials (redact `Cookie`/`password`).
- **Environment config:** `--dart-define=APP_ENV=dev|prod` in `core/config/env.dart`.
  `dev` pre-fills `http://localhost:8007` + verbose logging; `prod` defaults to the
  last-used profile. Named flavors (`flutter run --flavor dev`) are optional MVP sugar.
- **App lifecycle:** `LifecycleObserver` (`app/lifecycle_observer.dart`, a
  `WidgetsBindingObserver`) on `AppLifecycleState.resumed` → `GET /health` +
  `GET /api/auth/me` (revalidate session), then `ref.invalidate` active feature
  providers and reconnect any SSE subscription; `paused` → cancel SSE subscriptions
  (mobile OSes throttle background sockets). Reconnect uses capped exponential backoff.
- **Theming:** all theme files live in **`lib/app/theme/`** (`theme.dart`,
  `tokens.dart`, `typography.dart`). Tokens port the web brand — the design doc
  (separate deliverable) owns the values; this spec only fixes the location and the
  `ThemeData.from(colorScheme)` assembly point so both docs stay compatible.

---

## 5. Testing strategy & lints

- **Unit tests** (`test/`, run: `flutter test`):
  - *Repositories* — mock `dio.httpClientAdapter` (mocktail) or inject a mock `Dio`;
    assert path resolution (`platformPath` legacy vs scoped), query params, and the
    `DioException → AppException` mapping table.
  - *Controllers* — real `ProviderContainer` with repository overrides; assert
    family isolation: seeding `galleryControllerProvider('a')` must not affect `'b'`.
  - *SSE parser* — golden frame fixtures from `research.py` (`data:` frames, the
    terminal `event: done`, frames split across chunk boundaries, CRLF).
  - *Auth* — cookie jar save/load round-trip with mocked storage; 401 interceptor
    triggers exactly one `forceLogout`.
- **Widget tests:** screens pumped with overridden controllers — login form error
  display, gallery empty/error/retry states, platform card statuses.
- **Golden tests** (`test/golden/`): platform hub, gallery grid, process monitor,
  login. Disable `google_fonts` HTTP fetch in tests (load bundled font bytes in
  `setUpAll`), pin surface size, review diffs in CI.
- **Integration tests** (`integration_test/`): `mock_backend.dart` starts a loopback
  `HttpServer` with canned JSON (`/health`, login + `Set-Cookie`, `/api/platforms`,
  `/api/records`) and an SSE endpoint; drives login → hub → gallery → process
  headless in CI (`flutter test integration_test`).
- **Lints:** `flutter_lints: ^6.0.0` plus `prefer_single_quotes`,
  `require_trailing_commas`, `unawaited_futures`, `prefer_final_locals`,
  `always_declare_return_types`, `avoid_print` (allowed in `tool/` only).
  CI gate: `flutter analyze` clean; no `// ignore:` without a reason comment.

---

## 6. Code-size discipline (for implementers)

Contract snippets above are the ceiling: ≤25 lines per illustrative block. No
monolithic files — a screen >400 lines or a datasource >200 lines gets split.
DTO dumps, generated JSON mappers, and copied backend schema definitions belong
in code, not in docs.

---

## 7. Risks / open questions

1. **Legacy path migration.** `/api/records` etc. are Adobe-only top-level today;
   `platform_paths.dart` is the single seam that flips when
   `/api/platforms/adobe_stock/...` lands (known ARCHITECTURE.md migration candidate).
   Mobile must not invent its own scoping.
2. **SSE through Cloudflare tunnels** — intermediary buffering/idle timeouts can stall
   `text/event-stream`. Mitigation: backend keep-alive comments (if added) + client
   backoff/reconnect; verify with a real tunnel before ship.
3. **Cleartext HTTP:** LAN backends are `http://` — needs Android
   `usesCleartextTraffic`/network-security config scoped to LAN hosts, and an iOS ATS
   exception. Do not disable ATS globally.
4. **`localhost` ≠ device:** Android emulator → `10.0.2.2`, iOS sim → `localhost`,
   physical device → machine LAN IP. The profile editor's placeholder text must say so.
5. **Version drift / fonts:** pins verified 2026-10-15 — re-verify with
   `flutter pub upgrade --dry-run` at implementation start; `google_fonts` fetches
   at runtime and fails offline, so bundle the used families as assets before beta.
