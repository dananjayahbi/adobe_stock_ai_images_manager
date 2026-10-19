# 04 — Mobile UI Design System

> Part of the AI Stock Studio mobile plan. Mirrors the web brand in
> `frontend-new/tailwind.config.ts` ("vintage batch studio": leather, parchment,
> ink, brass, oxblood) into Flutter primitives. Dark-only for MVP. Every spec
> here is normative — screens in `05-screen-inventory.md` consume it.

---

## 1. Theme foundation

### 1.1 ColorScheme mapping (Material 3, `ColorScheme.dark` overrides)

Tokens are copied verbatim from the web Tailwind config — no reinterpretation.

```dart
// lib/app/theme/app_colors.dart
abstract final class AppColors {
  // parchment — leather surfaces (50 = card sheet, 100 = deep page bg)
  static const parchment50  = Color(0xFF2B2119);
  static const parchment100 = Color(0xFF201812);
  static const parchment200 = Color(0xFF362A20);
  static const parchment300 = Color(0xFF423427);
  static const parchment400 = Color(0xFF4F3F2E); // hairline border
  static const parchment500 = Color(0xFF6B563E);
  // ... 600–900, ink 50–900, brass, oxblood, olive, rust as in tailwind.config.ts
  static const leatherBg    = Color(0xFF1A130C); // page chrome (#1a130c)
}
```

| ColorScheme role      | Token                              | Rationale |
|-----------------------|------------------------------------|-----------|
| `primary`             | `oxblood-500 #8b3a2f`              | Red-wax-seal CTA (matches web `Button`) |
| `onPrimary`           | `ink-50 #f7efdd`                   | 6.69:1 on oxblood-500 |
| `primaryContainer`    | `oxblood-600 #742f26`              | Pressed/disabled-fill container |
| `onPrimaryContainer`  | `ink-50 #f7efdd`                   | 8.43:1 |
| `secondary`           | `brass-400 #cba857`                | Gilded accents, rules, badges |
| `onSecondary`         | `ink-900 #17110a`                  | 8.28:1 on brass-400 |
| `surface`             | `parchment-100 #201812`            | Default page bg |
| `surfaceContainer` (card) | `parchment-50 #2b2119`          | Card sheet |
| `surfaceContainerLow/High` | `parchment-100` / `parchment-200` | Inset / raised states |
| `surfaceVariant`      | `parchment-200 #362a20`            | Sheets, dialogs |
| `outline`             | `parchment-400 #4f3f2e`            | Hairline borders (decorative) |
| `outlineVariant`      | `parchment-300 #423427`            | Dashed dividers, faint rules |
| `onSurface`           | `ink-800 #eee3cc`                  | Primary text (13.7:1) |
| `onSurfaceVariant`    | `ink-400 #a29175`                  | Muted/caption text — see §4 contrast guard |
| `error` / `errorContainer` | `rust-500 #a15f26` / `rust-600 #824a1c` | Failures |
| `onError`             | `ink-50 #f7efdd`                   | |
| `tertiary`            | `olive-400 #9db066`                | Success ("olive") |
| `scrim`               | `ink-900 #17110a` @ 72%            | Modals, viewer chrome |

- Scaffold background: **leather `#1a130c`** with a subtle radial warm glow +
  paper grain overlay (see §8.2); cards sit on `parchment-50`.
- `useMaterial3: true`; disable `surfaceTintColor` everywhere
  (`surfaceTintColor: Colors.transparent`) — Material's blue tint would break
  the warm palette.

### 1.2 Typography

Google Fonts via the `google_fonts` package. Roles mirror web
`font-display` / `font-body` / `font-stamp` / `font-script`.

| Role | Family | Use | Size / line-height |
|------|--------|-----|--------------------|
| `display` | **Playfair Display** (600/700) | Hero titles, screen titles | 28/34 (screen), 34–40 (hero) |
| `section` | Playfair Display (600) | Card & section headings | 20/26 |
| `body` | **EB Garamond** (400/500) | Body, list rows, buttons | 16/24 (min 12sp for tertiary notes) |
| `bodySmall` | EB Garamond | Supporting text | 14/20 |
| `caption` | EB Garamond | Timestamps, helper text | 12/16 |
| `labelCaps` | EB Garamond 600, `letterSpacing 0.18em`, UPPERCASE | 11/14 — eyebrows, meta labels (web `label-caps`) |
| `stamp` | **Special Elite** | Postmark badges, status stamps, IDs | 12–16/18 |
| `script` | **Pinyon Script** | Flourishes only (`batches` accent, corner ✦) | 22–28 |

```dart
TextTheme _buildTextTheme(TextTheme base) => base.copyWith(
  displaySmall: GoogleFonts.playfairDisplay(
    fontSize: 28, height: 1.21, fontWeight: FontWeight.w700,
    color: AppColors.ink800),
  bodyMedium: GoogleFonts.eBGaramond(
    fontSize: 16, height: 1.5, color: AppColors.ink800),
  labelSmall: GoogleFonts.eBGaramond(
    fontSize: 11, height: 1.27, fontWeight: FontWeight.w600,
    letterSpacing: 2, color: AppColors.ink400),
);
```

Rules: body ≥ 12sp; line-height ≈ 1.5 for body, 1.2 for display; never use
Pinyon Script for anything a user must read to operate the app.

### 1.3 Spacing, radius, elevation

| Scale | Value |
|-------|-------|
| `space1/2/3/4/6/8` | 4 / 8 / 12 / 16 / 24 / 32 dp |
| Screen padding | 16 dp sides; card padding 16–20 dp |
| `radiusSm` | 4 dp (buttons, chips, inputs) |
| `radiusMd` | 8 dp (cards, dialogs, sheets) |
| `radiusFull` | pill (status chips only) |

Vintage motif prefers **crisp corners** — cap at 8 dp; no 16 dp+ rounding.

Elevation (no purple-ish Material surfaces; shadows are warm-black only):

| Token | Shadow | Use |
|-------|--------|-----|
| `card` | `0 1px 2px rgba(0,0,0,.45), 0 8px 24px -16px rgba(0,0,0,.7)` | AppCard |
| `raised` | `0 2px 4px rgba(0,0,0,.5), 0 16px 40px -20px rgba(0,0,0,.8)` | FAB, bottom sheets, pressed card |
| `seal` | inset `0 0 0 1px rgba(203,168,87,.35)` | Brass inner ring on CTAs/badges |

Implement via `BoxDecoration(shadows: [...])` or `CardTheme.elevation: 0` +
custom shadow — never Material's default colored elevation.

### 1.4 AppBar & BottomNav

- **AppBar**: transparent → leather at scroll (blurred `BackdropFilter`), height
  56 + top safe area, title in `display` 20sp, no default elevation; bottom edge
  = 1px `parchment-400` hairline. Leading actions ≥ 44×44 dp.
- **BottomNavigationBar** (shell, ≤5 tabs): leather bg `#1a130c`, top
  double-hairline (1px `parchment-400` + 1px gap + 1px), height 60 + bottom
  safe area. Labels: `labelCaps` 11sp. Selected: brass icon+label + 24 dp brass
  indicator rule above icon + haptic tick (§8.4). Unselected: `ink-400`.
  `type: fixed`, no shifting (fixed feels more "printed ticket").

---

## 2. Core widget inventory

All in `lib/core/widgets/`; screens must compose these, not re-roll styles.

| Widget | Purpose |
|--------|---------|
| **AppCard** | Signature double-hairline frame: outer 1px `parchment-400`, 3px gap, inner 1px `parchment-400` at 40% opacity, `parchment-50` fill, `card` shadow, 8 dp radius. `child`, optional `cornerFlourish` (script ✦ in brass). |
| **LabelCaps** | 11sp uppercase letterspaced text — eyebrows, card meta labels. |
| **StampBadge** | Rotated (−2° default) postmark: dashed `stadium` border + `stamp` font text; variants `brass` / `olive` / `rust` / `muted`. Used for statuses and IDs. |
| **StampIn** | Wrapper applying the stamp-in animation (§3) to any child — status stamps, CTA confirmations. |
| **DashedDivider** | 1px dashed rule in `parchment-400` (ticket perforation). |
| **PrimaryButton** | Oxblood fill (`oxblood-500`, pressed `oxblood-600`), `onPrimary` text, brass `seal` inset, min 48 dp high × ≥44 dp touch. Loading = inline brass spinner, keeps width. |
| **SecondaryButton** | Outline: `parchment-400` border, `ink-800` label, brass border on hover/press. Same metrics. |
| **GhostButton** | Text-only, `oxblood-400` label, ≥44 dp hit box (padding, not text size). |
| **StatusChip** | Pill: tinted bg (state@12%) + state color icon + **text label** (never color alone): `olive` approved/passed, `rust` failed/blocked, `brass` processing/pending, `ink-400` idle, `oxblood` attention. |
| **SkeletonLoader** | Parchment-300 block + subtle shimmer (§3), `aria-busy` semantics. Variants: card, grid tile, list row. |
| **EmptyState** | Centered: stamp-font illustration glyph or dashed frame, Playfair headline, EB Garamond body, optional PrimaryButton. |
| **ErrorState** | Inline, near-context (inside the card/list that failed) — dashed rust frame, rust icon + message + GhostButton "Retry". Not a full-screen takeover. |
| **ToastException** | Transient snack: leather sheet, brass left rule, stamp-font `ERROR`/`OK` eyebrow + message; success auto-dismiss 2.5 s, errors persist. Use `Semantics liveRegion`. |
| **HeroImageFrame** | Dashed parchment mat + hairline around every thumbnail; `Hero(tag: recordId)` source for gallery→detail. |
| **ProgressBar** | Track `parchment-300`, fill `brass-400`→`brass-500` gradient, optional stamp-font `%` label. |
| **LiveDot** | 8 dp olive dot, pulsing opacity + halo; paired with "LIVE" `labelCaps` — signals an active SSE/progress stream. |
| **ConnectionProfileBanner** | Full-width strip under AppBar: healthy = olive dot + profile name; degraded = rust icon + message + tap-to-retry health check. Drives the offline story (§4 of doc 05). |

Supporting: `PageHeader` (labelCaps eyebrow + Playfair title + layered rule
lines, matching web settings header), `DoubleRule`, `FlourishCorners`.

---

## 3. Motion spec

| Animation | Duration | Curve | Where |
|-----------|----------|-------|-------|
| Screen enter (fade-up) | **400 ms** (0 delay) | `easeOutCubic` | Route transitions, list entrances |
| Screen exit | **240 ms** (faster than enter) | `easeInCubic` | Route pops |
| Fade-up element stagger | 400 ms, +60 ms/child, capped at 6 | `easeOutCubic` | Cards, grid tiles |
| **Stamp-in** | **350 ms** | springy `cubicBezier(0.2, 0.9, 0.3, 1.4)` | Badges, APPROVED/REJECTED stamps, success CTAs |
| Hero gallery→detail | 350 ms | `easeOutCubic` (shared-axis Z) | Image + frame |
| Skeleton shimmer | 1200 ms loop, opacity 0.4→0.7 | `easeInOut` | Loading states |
| Tab indicator slide | 220 ms | `easeOutCubic` | Bottom nav brass rule |
| Button press | 90 ms down / 140 ms up | — | Scale 0.98 + shadow drop |

- **fade-up**: `opacity 0→1`, `translateY 8→0` (matches web keyframes).
- **stamp-in**: `scale 1.15→1`, `rotate −6°→−2°`, `opacity 0→1` — ends at the
  signature −2° tilt, same as web.
- **Haptics**: `HapticFeedback.mediumImpact` on approve commit;
  `lightImpact` on bottom-nav tab change; `selectionClick` on chip toggles.
  Never haptic on mere page load.
- **Reduced motion**: honor `mediaQuery.disableAnimations` (and an in-app
  Settings toggle): replace stamp-in/fade-up/stagger with instant opacity 1,
  stop shimmer (static block), keep haptics (they are not motion).
- Implement with `flutter_animator`-free primitives: `AnimationController` +
  `CurvedAnimation`, or `TweenAnimationBuilder` for one-shot entrances.

---

## 4. Accessibility rules

Touch targets: **≥44 dp (iOS) / 48 dp (Android)** — use 48 dp as the Flutter
floor — with **≥8 dp spacing** between adjacent targets.

| Pair (role) | Ratio | Verdict |
|---|---|---|
| ink-800 on parchment-100 (body on page) | 13.74 | ✅ |
| ink-800 on parchment-50 (body on card) | 12.36 | ✅ |
| ink-600 on parchment-100 (secondary) | 9.03 | ✅ |
| ink-400 on parchment-100 (caption) | 5.70 | ✅ |
| ink-400 on parchment-200 | 4.54 | ✅ (barely — avoid for <14sp) |
| **ink-400 on parchment-300** | **3.91** | ❌ **fails** → use ink-600 (6.19) |
| **ink-400 on parchment-400** | **3.29** | ❌ **fails** → use ink-200 (6.19) |
| **olive-500 as text on parchment-100** | **2.73** | ❌ **fails** → text must use olive-400 (7.36); olive-500 is fill-only |
| **rust-500 as text on parchment-100** | **3.48** | ❌ **fails** → text must use rust-400 (7.54) |
| **oxblood-400 on parchment-200** | **4.43** | ❌ marginal → use oxblood-300 `#e09a8f` (6.09) for text on raised surfaces |
| ink-50 on oxblood-500 (button label) | 6.69 | ✅ |
| brass-400 / olive-400 / rust-400 on parchment-100 | 7.7 / 7.4 / 7.5 | ✅ |
| ink-400 on leather bg `#1a130c` | 5.99 | ✅ |
| **parchment-400 hairline vs surface** | 1.73 | ⚠ decorative only — never the sole indicator of an interactive boundary; use parchment-600 (3.76) for meaningful borders (inputs, focus) |

Additional rules:

1. **Never state-by-color alone**: every StatusChip/StatusStamp pairs color
   with an icon **and** text (e.g. olive + check + "APPROVED").
2. **Semantics**: icon-only buttons get `Semantics(label: ...)` (e.g.
   "Approve image", "Retry"); images get `semanticLabel` = record title;
   LiveDot marked `liveRegion: true`.
3. **Screen-reader order** = visual order: header → context banner → content →
   primary action → secondary; grids announce "n of total".
4. **Safe areas**: respect `MediaQuery.padding` on all four sides; bottom nav
   adds `padding.bottom`; immersive image viewer temporarily ignores status bar
   but keeps gesture nav inset.
5. **Dynamic Type caution**: serif families (EB Garamond, Playfair) scale
   poorly above ~130%. Allow scaling to 130% for body; cap display at ~120% and
   re-test wraps; never `maxLines: 1` on a required label without
   `overflow: ellipsis` + full text in semantics.

---

## 5. Image handling

- **Package**: `cached_network_image` (+ `flutter_cache_manager` for a 500 MB /
  7-day LRU disk cache; clear on Settings → Storage).
- **Two tiers**:
  - Grid/tile: request `thumbnailUrl` (~320 px long edge) — cheap, parallel,
    `memCacheWidth: 320` decode hint.
  - Detail/zoom: fetch full-res lazily on page open, show thumbnail blurred/
    scaled behind until decoded (cross-fade 200 ms).
- **Placeholder**: `shimmer` skeleton in `parchment-300` inside `HeroImageFrame`
  (aspect-locked, no layout jump).
- **Error fallback**: dashed `parchment-400` frame + rust
  `image-not-loaded` icon + tappable retry (inline ErrorState, not toast).
- **Zoomable detail**: `InteractiveViewer` (min 1.0, max 4.0, double-tap 2.0),
  constrained=false over a fitted base image; page swipes use a horizontal
  `PageView` — gesture arena wins: horizontal drag = next/prev image, once the
  zoom is at 1.0; otherwise pan wins.
- Progressive JPEG / `ResizeImage` for large full-res files.

---

## 6. Iconography

- **Single family: Lucide** via `lucide_flutter` — the web frontend ships
  `lucide-react ^0.330.0`, so mobile gets **icon parity with the brand** for free
  (this overrides any preference for other families). **No emoji anywhere**
  (including flourishes — the web's `✦` is rendered as a glyph/text, keep it as
  styled text, not an emoji).
- Usage: default weight `regular`; `fill` only for selected bottom-nav icons;
  `bold` for status icons inside stamps/chips.
- Sizes: 20 dp in buttons/chips · 24 dp nav + list icons · 32 dp empty/error
  states · 48 dp large feature glyphs. Color always from theme roles
  (`onSurfaceVariant`, state color), never hardcoded per screen.

---

## 7. Theme scope

- **MVP is dark-only**: `darkTheme: appTheme`, `themeMode: ThemeMode.dark`,
  no system-follow. The vintage brand *is* the dark leather identity; a light
  theme (true parchment paper) is a deliberate future project — do not leave
  half-built light tokens behind, but keep `ColorScheme` role-mapping clean so
  a light variant can slot in later.

---

## 8. "Wow" showcase elements

Tasteful, on-brand moments — leather & brass, never glassmorphism or purple
gradients.

1. **Login stamp-in logo** (§3): the "AI Stock Studio" postmark badge scales in
   1.15→1.0 rotating −6°→−2° with a medium haptic as it lands, on grain
   leather. Form fields then fade-up staggered +60 ms.
2. **Leather background with subtle parallax**: page bg = `#1a130c` + radial
   warm glow + tiled grain SVG. The grain layer scrolls at ~0.9× scroll offset
   (max 12 dp drift) — barely perceptible, reads as "material depth."
3. **Brass tab indicator + haptic tick**: bottom-nav brass rule slides between
   tabs (220 ms) with `lightImpact`; tab icon swaps to `fill` weight.
4. **Animated status stamps**: on approve success (and other review actions) the result stamp
   ("APPROVED" / "REJECTED", Special Elite, rotated −2°, dashed ring) slams in
   over the image with stamp-in + medium haptic, then settles into the
   metadata card as its status chip.
5. **Staggered grid entrance**: gallery tiles fade-up in a 60 ms diagonal
   stagger on first load / filter change — 6 max, then instant.
6. **Double-hairline framing everywhere**: cards, dialogs, and the image mat
   all carry the engraved-certificate double rule + corner flourishes — the
   single most recognizable web motif, reproduced faithfully.

---

## 9. Dependencies (UI layer)

```yaml
# Versions authoritative in 03 §1 (verified on pub.dev 2026-10-15).
dependencies:
  google_fonts: ^9.0.0        # Playfair, EB Garamond, Special Elite, Pinyon Script
  lucide_flutter: ^1.47.0     # icon family (single family rule; parity with web lucide-react)
  cached_network_image: ^4.0.4  # image cache (flutter_cache_manager comes transitively)
```

Skeleton shimmer, fade-up, and stamp-in are implemented with **Flutter animation
primitives** (`Animated*`, `AnimationController` + curves) per 03 §1 — no extra
animation/shimmer packages.

All snippets in this doc are illustrative fragments (≤20 lines) — final APIs
live in `lib/app/theme/` (tokens/typography) and `lib/core/widgets/` (shared
widgets).
