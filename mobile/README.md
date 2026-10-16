# AI Stock Studio — mobile app (Flutter)

The remote control for the studio: review gallery images, run pipelines, and
watch live progress from a phone — anywhere, over a Cloudflare tunnel. The
full implementation plan lives in [`../mobile-plan/`](../mobile-plan/README.md).

## Commands

```powershell
flutter pub get
flutter analyze          # zero issues expected
flutter test             # 312 tests — the integration gate
flutter build apk --release   # → build/app/outputs/flutter-apk/app-release.apk (55 MB)
flutter build apk --debug     # → build/app/outputs/flutter-apk/app-debug.apk (unminified)
flutter build web --release  # → build/web (browser preview / E2E)
```

## Connection profiles

- **Tunnel** — `https://studio.hotelgo.lk` (named Cloudflare tunnel → :8007).
  This is the **only seeded profile** — the app is tunnel-first by design:
  localhost URLs on a phone are the phone itself, never the PC.
- **LAN / emulator** — add manually after login via *Settings → CONNECTION →
  Add*, e.g. `http://192.168.1.244:8007` (PC's LAN IP) or
  `http://10.0.2.2:8007` (Android emulator → host). Each profile is
  health-checked before it can become active.

Profiles are per-platform-session scoped: each profile stores its own
`studio_session` cookie so LAN and tunnel logins never cross.

**Reachability handling** (important on a phone):

- At boot, splash runs the health-gated **auto-fallback**: if the active
  profile's `/health` fails, the other profiles are probed in order and the
  first reachable one is activated before any session/API traffic fires.
- The **login screen** shows a `CONNECTION` row (active profile + host) that
  opens a profile picker *before* authentication — every switch is
  health-checked, and a dead host keeps the current profile with the reason
  inline.

### DNS fallback (why the app resolves when the phone doesn't)

Some Android devices' **system** resolver fails for a name that Chrome opens
fine — Chrome runs its own DoH, so "the browser works" proves the network,
not the resolver. The app therefore doesn't depend on the device's DNS:

1. **Pre-check** — `HealthApi.probe` resolves the host up front via
   `DnsResolver`: system lookup first, then a plain UDP/53 chain
   (8.8.8.8 → 1.1.1.1 → NextDNS). A miss returns the exact
   `Host unreachable. (Failed host lookup: …)` copy plus the Private DNS
   hint — before any socket attempt.
2. **Relay** — at bootstrap a loopback HTTP **CONNECT** proxy starts and
   `HttpOverrides` routes every *name-based* request through it (literal
   IPs/localhost stay direct). The proxy re-resolves with the same chain and
   pipes bytes; TLS/SNI stays end-to-end, so certificates are untouched.
3. The web build skips all of this — the browser resolves (usually via DoH).

## Web build & browser E2E notes

The web target exists as a quick preview/E2E harness (the product targets
Android/iOS). To serve it behind an origin your backend's CORS list allows:

1. `flutter build web --release`
2. Copy `build/web/*` → `../frontend-new/public/flutter/` (git-ignored).
3. Patch `<base href="/">` → `<base href="/flutter/">` in the copied
   `index.html` (equivalent of building with `--base-href /flutter/`).
4. Start the backend with that origin in `CORS_ORIGINS`, open
   `http://localhost:<port>/flutter/index.html`.

Behavior notes discovered during E2E:

- Dio rides the **browser cookie jar** on web via
  `extra: {'withCredentials': true}` in `BaseOptions` (the CookieManager's
  `Cookie` header is a forbidden header in browsers; native is unaffected).
- Pre-login the backend's auth middleware (deliberately outside CORS) answers
  unauthenticated `/api/auth/me` probes without CORS headers — console noise
  in web devtools; login is whitelisted and works.
- In-image thumbnail headers are ignored by browser `<img>` — thumbnails ride
  the ambient cookie jar; the native app replays the header explicitly.

## Architecture

Modular, feature-first layout (see [`../mobile-plan/04-architecture.md`](../mobile-plan/04-architecture.md)):

```
lib/
  app/        # bootstrap, router (GoRouter + shell), theme, lifecycle
  core/       # config, network (Dio factory, SSE, cookie jar, DNS fallback
              # relay + resolver), storage, widgets, utils
  features/   # auth · hub · dashboard · gallery · process · delivery · settings
```