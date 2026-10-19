# Mobile App Implementation Plan — AI Stock Studio

**Status:** plan complete · **implemented** (milestones M0–M5 gated; M6 release in progress) · **App:** `mobile/` (repo root)

This directory is the full implementation plan for the Flutter mobile app that lets you
operate the studio remotely from a phone: review gallery images, run pipelines, and
watch live progress — over a Cloudflare tunnel when away, over LAN when home.

## Read in this order

| # | Document | What it answers |
|---|----------|-----------------|
| 1 | [01-vision-scope.md](./01-vision-scope.md) | Why this app, what's in/out of MVP, product flow, constraints |
| 2 | [02-api-integration-map.md](./02-api-integration-map.md) | Every backend endpoint, the mobile MVP subset, gaps, native-auth notes |
| 3 | [03-flutter-architecture.md](./03-flutter-architecture.md) | Packages (verified), `mobile/` folder tree, layer contracts, testing |
| 4 | [04-ui-design-system.md](./04-ui-design-system.md) | ThemeData from brand tokens, reusable widgets, motion, accessibility |
| 5 | [05-screen-inventory.md](./05-screen-inventory.md) | Every screen: routes, layout, states, gestures, endpoint traceability |
| 6 | [06-connectivity-cloudflare.md](./06-connectivity-cloudflare.md) | Named-vs-quick tunnel decision, Windows service, SSE behavior, security |
| 7 | [07-implementation-roadmap.md](./07-implementation-roadmap.md) | Milestones M0→M6 with file-level tasks, validation gates, risks |

## Headline decisions

- **Flutter + Riverpod + go_router + Dio** — talk directly to the FastAPI backend
  (:8007); no new backend-for-frontend. Versions pinned in [03](./03-flutter-architecture.md).
- **Cloudflare named tunnel** (stable hostname, Windows service, SSE-capable) with a
  **LAN profile** fallback — quick tunnels are disqualified because they don't support
  SSE ([06](./06-connectivity-cloudflare.md) §1).
- **Connection profiles** are a first-class app concept: named base URLs, `GET /health`
  check on switch, `studio_session` cookie stored per profile.
- **Same brand, native form factor** — dark leather/parchment tokens, Playfair/EB
  Garamond/Special Elite type, stamp-in motion, Lucide icons (parity with the web's
  `lucide-react`); 5-tab shell
  with a full route tree ([04](./04-ui-design-system.md), [05](./05-screen-inventory.md)).
- **Per-platform isolation preserved** — `platformId` travels on API calls; Riverpod
  `.family(platformId)` providers keep state separate, mirroring the backend contract.
- **MVP = no local database** — server is the source of truth; the app caches images and
  holds only session/connection-profile state.

## Key facts for implementers

- Backend is universal-platform already: `GET /api/platforms/` (note **trailing slash** —
  naive clients hit a 307), Adobe Stock lives under legacy paths, everything else under
  `/api/platforms/{id}/...` ([02](./02-api-integration-map.md) §2).
- Images/thumbnails are **behind auth** and DB paths are absolute → the client sends the
  cookie and passes basenames ([02](./02-api-integration-map.md) §4).
- Jobs are in-memory: **404 after a backend restart** — screens must handle it
  gracefully ([02](./02-api-integration-map.md) §16).
- SSE frames end with `event: done` / `data: {}`; consume via Dio stream + local parser,
  never plain `EventSource` ([03](./03-flutter-architecture.md), [06](./06-connectivity-cloudflare.md) §3).

## Definition of Done (MVP)

On a **physical phone**, via tunnel *and* LAN: boot → login → browse gallery → run a
pipeline with live SSE progress → approve an image → switch connection profile —
`flutter analyze` clean, `flutter test` green, release APK built.

See [07](./07-implementation-roadmap.md) for the milestone-by-milestone path.
