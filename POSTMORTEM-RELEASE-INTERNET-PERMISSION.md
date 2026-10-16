# Postmortem — Release APK with no network on device (missing INTERNET permission)

**Status:** fixed and verified (release APK sha `08409D82`, badging lists
`android.permission.INTERNET`, `apksigner verify` = OK).
**Impact:** the first shipped release builds could not reach the studio from
any physical phone; debug builds, emulators, and browsers all worked.

---

## 1. The issue (as it presented)

On two physical Android devices, the installed **release** APK could not
log in:

- Login banner: `Can't reach the studio server. Check your network and
  connection profile.`
- Connection editor: `Host unreachable. (Failed host lookup:
  'studio.hotelgo.lk' (OS Error: No address associated with hostname,
  errno = 7))`

While:

- the **same URL opened fine in the phone's browser**,
- the app **worked in the Android emulator**,
- the Flutter **web build worked everywhere**.

The on-device **Network diagnostics** screen (built during this
investigation) produced the decisive evidence:

| Row | Result |
|---|---|
| System resolver | red — `Failed host lookup … errno = 7` |
| DoH 1.1.1.1 (IPv4) | red — `Connection failed … errno = 1` |
| DoH 2606:4700:4700::1111 (IPv6) | red — `Connection failed … errno = 1` |
| UDP 8.8.8.8:53 | red — `Failed to create datagram socket … errno = 1` |
| Full resolver chain | **green** (returned pinned IPs — no socket I/O) |
| Relay (CONNECT proxy) | red — `relay not running` (bind failed) |
| TLS egress 1.1.1.1:443 | red — `Connection failed … errno = 1` |
| Tunnel /health (direct & app path) | red — `errno = 7` |

## 2. Why it happened

**The release build had no `android.permission.INTERNET`.**

The Flutter project template declares `INTERNET` only in:

- `android/app/src/debug/AndroidManifest.xml`
- `android/app/src/profile/AndroidManifest.xml`

`src/main/AndroidManifest.xml` — the only manifest merged into a
**release** build — had no `<uses-permission>` at all. Verified two ways:

```text
# grep across android/  → only debug + profile carry INTERNET
# aapt dump badging app-release.apk
uses-permission: name='com.aistockstudio.ai_stock_studio.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION'
                  # ← no android.permission.INTERNET
```

Without that permission the kernel/SELinux denies **every `socket()`** in
the process with `EPERM (errno = 1)` — UDP creation, TCP connect (both
address families), and even loopback `ServerSocket.bind` (hence the dead
relay). System DNS also needs sockets, which is why it surfaced as the
misleading `errno = 7` hostname error.

It hid behind three confounders:

1. **Debug/emulator runs worked** — the debug manifest supplies the
   permission, so the failure looked release-specific-network or
   device-specific.
2. **Browsers/webviews worked** — Chrome carries its own permission; the
   tunnel itself was fine.
3. **`Full resolver chain` showed green** — the chain's last tier returns
   *pinned IPs* for the tunnel host without performing any I/O, so
   "resolution works" coexisted with "no sockets allowed".

## 3. How it was solved

1. **Diagnosis:** the diagnostics screen showed `errno = 1` on *every*
   socket (v4 + v6 + UDP + bind) — a permission/firing-line failure, not a
   DNS or routing failure. `aapt dump badging` confirmed the missing
   permission.
2. **Fix** in `mobile/android/app/src/main/AndroidManifest.xml`:

   ```xml
   <uses-permission android:name="android.permission.INTERNET"/>
   ```

3. **Rebuild + verify:**

   ```powershell
   flutter build apk --release
   aapt dump badging build\app\outputs\flutter-apk\app-release.apk |
       findstr uses-permission        # INTERNET present
   apksigner verify <apk>             # exit 0
   ```

4. **Result:** installed on the affected phones → all diagnostics rows
   green (system-resolver row may legitimately stay red on
   resolver-broken networks — that is what the fallback chain is for) and
   login succeeded over the tunnel.

> Debugging note: several genuinely useful hardening tiers were built
> before the real cause surfaced (DNS-over-HTTPS with dual-stack
> endpoints, AAAA lookups, pinned tunnel IPs, racing IPv4/IPv6 connects,
> the CONNECT relay, the diagnostics screen). They remain — but the
> **permission check must always come first**: it is the cheapest
> hypothesis and the most common cause of "everything is EPERM".

## 4. Prevention

- **Repo:** the permission now lives in `main/AndroidManifest.xml` with a
  comment; [`mobile/README.md`](mobile/README.md) carries a release-build
  gotcha note.
- **Global (all future projects):** a user-level instruction —
  `android-release-internet-permission.instructions.md` in the VS Code
  profile `instructions/` folder — triggers on manifest edits and on
  release-network failure phrasing (`EPERM`, `Operation not permitted`,
  release can't connect), and mandates the `aapt dump badging` check
  before shipping an APK.
