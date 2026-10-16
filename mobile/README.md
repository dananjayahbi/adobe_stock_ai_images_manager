# AI Stock Studio — mobile app (Flutter)

The remote control for the studio: review gallery images, run pipelines, and
watch live progress from a phone — anywhere, over a Cloudflare tunnel. The
full implementation plan lives in [`../mobile-plan/`](../mobile-plan/README.md).

## Commands

```powershell
flutter pub get
flutter analyze          # zero issues expected
flutter test             # 366 tests — the integration gate
flutter build apk --release   # → build/app/outputs/flutter-apk/app-release.apk (55 MB)
                              #   (build/app/outputs/apk/release/app-release.apk is the
                              #    Gradle twin — byte-identical; use flutter-apk/)
flutter build apk --debug     # → build/app/outputs/flutter-apk/app-debug.apk (unminified)
flutter build web --release --base-href /flutter/   # served at /flutter (below)
dart run flutter_launcher_icons                    # regen icons after tool/gen_logo.py
```

> **Release-build gotcha (fixed, kept for awareness):**
> `android.permission.INTERNET` must stay in
> `android/app/src/main/AndroidManifest.xml` — Flutter's template only adds
> it to *debug/profile* manifests, and a release build without it fails
> **every socket** on device with `Operation not permitted (errno 1)`
> (relay bind, UDP, TCP, system DNS) while browsers keep working.

## Connection profiles

- **Tunnel** — `https://studio.hotelgo.lk` (named Cloudflare tunnel → :8007).
  This is the **only seeded profile** — the app is tunnel-first by design:
  localhost URLs on a phone are the phone itself, never the PC.
- **Upgrade migration**: installs that still carry the old first-run
  `[local, tunnel]` seed drop the localhost profile on the first launch
  (one-time flag `migrated_legacy_local_v1`; active is reassigned to the
  tunnel). Profiles you add yourself afterwards are never touched.
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
not the resolver. Worse, some networks **block or hijack plain UDP/53**
while HTTPS works. The app therefore resolves in three tiers and never
depends on the device's DNS:

1. **Pre-check** — `HealthApi.probe` resolves the host up front via
   `DnsResolver`, a four-tier chain:
   - the system resolver first (fastest, honours local configuration);
   - then **DNS-over-HTTPS**, dual-stack: four IP-literal endpoints —
     Cloudflare `1.1.1.1` + `2606:4700:4700::1111`, Google `8.8.8.8` +
     `2001:4860:4860::8888` — each asked for **A and AAAA** in parallel.
     IP literals need no lookup, both providers' certs carry matching IP
     SANs, and covering *both* families fixes phones whose IPv4 egress is
     broken while IPv6 works (or the reverse) — the exact split where the
     browser resolves but the OS and plain UDP/53 fail;
   - then a plain UDP/53 chain (8.8.8.8 → 1.1.1.1 → NextDNS), 2 s per
     server, as the last network-dependent tier;
   - then the **pinned tunnel IPs** (Cloudflare edge A + AAAA records of
     `studio.hotelgo.lk`) — a zero-DNS escape hatch: Cloudflare serves any
     orange-clouded host by SNI, so a known-good address works even when
     every resolver is dead.

   A miss returns the exact `Host unreachable. (Failed host lookup: …)`
   copy plus the Private DNS hint — and notes that DoH + public resolvers
   were tried too, so total-failure reports are diagnosable.
2. **Relay** — at bootstrap a loopback HTTP **CONNECT** proxy starts and
   `HttpOverrides` routes every *name-based* request through it (literal
   IPs/localhost stay direct). The proxy re-resolves with the same chain
   and **races every resolved address — IPv4 and IPv6 — in parallel**, so
   whichever family the phone can reach wins; TLS/SNI stays end-to-end,
   so certificates are untouched.
3. The web build skips all of this — the browser resolves (usually via DoH).

### Network diagnostics (on-device)

`Settings → Connections → Network diagnostics` — and, pre-login, the
**CONNECTION** sheet's *Network diagnostics…* button — opens a
layer-by-layer ladder: system resolver · DoH (IPv4) · DoH (IPv6) · UDP ·
full resolver chain · relay · TLS egress · tunnel `/health` direct ·
tunnel `/health` through the app's real `HttpOverrides` path. Each row is
green/red with the **full, selectable, untruncated** error text — the
first red row is where the phone stops; screenshot it when reporting a
connection problem.

## Gallery lifecycle: one state, many flags

Exactly one **state** per image — `COLLECTED` (non-processed) → `APPROVED`
(pipeline passed) / `REJECTED` (failed) → `READY_TO_PUBLISH` (manual queue
only) → `PUBLISHED` → `AS_ACCEPTED` — plus any number of **flags** rendered
together: `QUARANTINED`, `USED`/`UNUSED` (always exactly one of the two),
`METADATA_READY`, `INCOMPATIBLE`, `REFINED`, `UPSCALED`, `OCR_REJECTED`.

- `PATCH /api/records/{id}/state` performs the whitelisted manual moves;
  `POST …/approve` is the fast `APPROVED|REJECTED → READY_TO_PUBLISH` flip
  (no LLM/metadata regeneration — the old approve could block >10 s).
- Marking `USED` pushes the image to `PUBLISHED` (`AS_ACCEPTED` sticks) —
  used images only ever live in those two states.
- The pipeline `stage` column stays as an internal cursor for the Process
  screens; gallery, detail, filters and dashboard speak `state` + `flags`
  (`state=` query filter, `state_counts` on the summary endpoint).
- The startup migration (`services/migrations.py`) runs the legacy→state
  repair every boot as guarded idempotent statements — it can never
  overwrite a manual state, and it self-heals any drift.

## Launcher icon & favicon

The mark — a faceted studio aperture with AI sparkles, palette-matched to
`tokens.dart` — is generated, never hand-edited:

```powershell
..\backend\.venv\Scripts\python.exe tool\gen_logo.py   # assets/logo/*.png + favicon.ico
dart run flutter_launcher_icons                # → android res/ mipmaps + adaptive icon
Copy-Item assets\logo\favicon.ico web\favicon.ico -Force   # web favicon (once)
```

## Web build & tunnel serving

The web target is the app itself served through the Cloudflare tunnel
(same origin as the API — cookie auth just works):

1. `flutter build web --release --base-href /flutter/`
2. The backend mounts `mobile/build/web` at **`/flutter`** automatically
   (guarded — skipped if the directory doesn't exist), so the app is live at
   `https://studio.hotelgo.lk/flutter/` whenever cloudflared is up.
   `/flutter` is on the auth allowlist (static shell only — every `/api/*`
   call still requires the session cookie).
3. A browser E2E against the tunnel origin proves the full journey:
   login screen shows `TUNNEL · studio.hotelgo.lk` only (no localhost in
   `localStorage`), sign-in → hub → dashboard (161 records) → gallery, and
   `fetch('/api/auth/me')` answers 200 on the tunnel origin.

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