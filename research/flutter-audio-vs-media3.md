# Flutter audio stack vs Media3: current state

Research for [#2](https://github.com/NYJvanMuijlwijk/music-player/issues/2), feeding the stack decision ("Stack: Flutter or Kotlin + Media3?"). Checked 2026-11-19 against source code at named tags, release notes, and official docs. Where a claim rests on anything weaker, it says so.

**Stacks compared**

- **Flutter:** `just_audio` 0.10.6 + `audio_service` 0.18.19 (both by Ryan Heise). The Android side is Media3 ExoPlayer **1.4.1** (inside just_audio) plus the legacy `androidx.media:media:1.7.0` session library (inside audio_service).
- **Native:** Jetpack Media3 **1.11.1** (ExoPlayer + `MediaSessionService`/`MediaLibraryService`) with Kotlin + Compose.

**Note on the reference app.** Auxio is often called "Media3-based". It uses Media3 **ExoPlayer** only. Its session layer is the legacy `MediaSessionCompat`/`MediaBrowserServiceCompat` with hand-written state mirroring. It adopted Media3's session layer in 2024 and then dropped it (see §5).

## Summary

| Criterion | Flutter: just_audio + audio_service | Native: Media3 + Kotlin |
|---|---|---|
| **Maintenance** | One maintainer writes about 75–83% of all commits and does every merge since 2025. Each package had one release in 2026 (late June, AGP 9 build changes only). A 4-line Android PR has waited 13+ months. audio_service has 186 open issues. | Google team: 2,325 commits from 80 authors in 2026. Minor release every 3–5 months, plus patch releases. Stable 1.11.1 (2026-09-10); 1.12.0-beta01 (2026-11-11). |
| **Android 14–17 foreground service rules** | Manifest setup documented (mediaPlayback type and permission). The service leaves the foreground on pause by default. The README tells you to change that setting or ask users to turn off battery optimisation. The Android code never catches `ForegroundServiceStartNotAllowedException`. Nothing on Android 17 audio hardening. | `MediaSessionService` runs the foreground service and notification itself. It keeps the foreground service for 10 minutes after pause (since 1.6.0). Several foreground-service crash fixes landed in 1.10–1.11. Google's Android 17 page names Media3 as "not likely to be impacted". |
| **Media resumption and cold start without UI** | Android 11 resumption is supported (a "recent" root, children supplied from Dart). A cold start boots a whole FlutterEngine and runs the app's `main()` headlessly, on the main thread, from `Service.onCreate`. You write persistence and restore yourself. | Built in, off by default. You opt in with `MediaButtonReceiver` + `onPlaybackResumption()`. The system UI resumption card needs a `MediaLibraryService`. The callback also runs at boot to build the card. You write persistence (queue, metadata, position) yourself. |
| **Gapless, delay/padding trimming** | Gapless is claimed on Android; the engine is ExoPlayer. It is pinned to Media3 1.4.1 (2024-08-23), so it lacks the 2026 MP3 LAME/Xing trimming fixes. Audio offload is off by default since 0.10.5. | Handled by the extractors: LAME/Xing header and iTunSMPB (ID3 comment or MP4 user data). MP3 trimming accuracy was fixed in 1.11.0 (2026-08-05). |
| **Session state for external controllers** | Your Dart code builds every `PlaybackState`: controls, actions, position, processing state. audio_service turns that into `MediaSessionCompat`. That means two state machines (ExoPlayer, compat session) joined by app code over platform channels. | `MediaSession` derives state from the `Player` automatically and serves legacy and platform controllers. AVRCP browsing on API 36/37 was fixed in 1.11.0. |
| **UI/session sync after activity or process death** | One isolate and a cached FlutterEngine, shared by the activity and the service. Recent open Android issues sit exactly here: ANR in `onCreate`, commands dropped after the service is recreated, a second engine after dispose. | The UI connects through `MediaController` (asynchronous, released in `onStop`). Recent fixes include a deadlock, an NPE and lost Timeline UIDs. Open backlog not verified. |
| **F-Droid** | Feasible: Finamp (just_audio fork + audio_service) is built by F-Droid. The recipe needs the Flutter SDK srclib, `scandelete: .pub-cache`, and native deps rebuilt from source. Flutter 3.50.0's embedding still references Play Core classes; whether that trips the scanner today is unverified. | Plain Gradle build. Auxio is built by F-Droid. Its recipe vendors and patches a Media3 fork, which is only needed for the FFmpeg extension. |
| **INTERNET permission** | Not in release builds from these plugins. Flutter's debug and profile manifests add INTERNET for tooling. just_audio's localhost-proxy features (StreamAudioSource, LockCaching, proxied headers) need sockets. ExoPlayer brings in `ACCESS_NETWORK_STATE`. | No Media3 library manifest declares INTERNET. `common` and `exoplayer` declare `ACCESS_NETWORK_STATE`; `exoplayer` adds `WAKE_LOCK` in 1.11.1. Auxio strips `ACCESS_NETWORK_STATE` with `tools:node="remove"`. |

### Versions and dates

| Component | Latest | Date | Source |
|---|---|---|---|
| just_audio | 0.10.6 | 2026-06-29 (tag) | [CHANGELOG](https://github.com/ryanheise/just_audio/blob/just_audio-v0.10.6/just_audio/CHANGELOG.md), [pub.dev](https://pub.dev/packages/just_audio/changelog) |
| audio_service | 0.18.19 | 2026-06-30 (tag) | [CHANGELOG (minor)](https://github.com/ryanheise/audio_service/blob/minor/audio_service/CHANGELOG.md). A 0.18.20 entry (iOS fixes) is in the changelog but has no tag. |
| just_audio_background | 0.0.1-beta.17 | last touched 2026-06-29 | wraps audio_service ^0.18.18 ([pubspec](https://github.com/ryanheise/just_audio/blob/minor/just_audio_background/pubspec.yaml)) |
| Media3 inside just_audio | 1.4.1 | 2024-08-23 | [build.gradle.kts](https://github.com/ryanheise/just_audio/blob/minor/just_audio/android/build.gradle.kts) |
| Session lib inside audio_service | androidx.media 1.7.0 | n/a | [build.gradle.kts](https://github.com/ryanheise/audio_service/blob/minor/audio_service/android/build.gradle.kts) |
| Media3 stable | 1.11.1 | 2026-09-10 | [RELEASENOTES](https://github.com/androidx/media/blob/release/RELEASENOTES.md) |
| Media3 pre-release | 1.12.0-beta01 | 2026-11-11 | [RELEASENOTES (main)](https://github.com/androidx/media/blob/main/RELEASENOTES.md) |
| Flutter stable | 3.50.0 | tag on `stable` head, 2026-11-19 | `git ls-remote` on flutter/flutter |
| Auxio | 4.1.5 | 2026-08-03 | [CHANGELOG](https://github.com/OxygenCobalt/Auxio/blob/dev/CHANGELOG.md) |

---

## 1. Maintenance

### Flutter

- **Release cadence.** just_audio shipped 10 releases in 2025 (0.9.43 to 0.10.5) and one in 2026. That one, 0.10.6 (2026-06-29), only says "Support AGP 9. Migrate Android build files to .kts". Before it, the default branch was idle from 2025-09-04 (0.10.5) to 2026-06-29. audio_service follows the same pattern: 0.18.18 (2025-04-11), then 0.18.19 (2026-06-30, AGP 9 only). Dates come from git tags in both repos.
- **Recent substance.**
  - just_audio 0.10.0 (2025-04-16): new playlist API; `ConcatenatingAudioSource` deprecated.
  - just_audio 0.9.43 (2025-01-12): migrated to Media3 ExoPlayer 1.4.1.
  - just_audio 0.10.5 (2025-09-04): Android audio offload disabled by default "to prevent playback issues".
  - audio_service 0.18.18: compile/target SDK 35 and a fix for the `stopForeground` deprecation.
- **Android backend age.**
  - audio_service is Java on `androidx.media:media:1.7.0`, with compileSdk 35 and minSdk 19.
  - Its branches are `minor`, `major`, `master`, `feature/service_lifecycle` (last commit 2021), and a few others. None is a Media3 migration.
  - just_audio pins Media3 `1.4.1` and also pulls in the DASH, HLS and SmoothStreaming modules unconditionally.
  - Internally, just_audio still builds playlists with Media3's deprecated `ConcatenatingMediaSource` ([AudioPlayer.java](https://github.com/ryanheise/just_audio/blob/minor/just_audio/android/src/main/java/com/ryanheise/just_audio/AudioPlayer.java)). That class still exists, deprecated, in Media3 1.11.1.
- **Bus factor: effectively 1.** Computed from `git log` on each default branch (`minor`), excluding merge commits:
  - just_audio: Ryan Heise wrote 707 of 854 commits (83%). Since 2025 he wrote 46 of 51, and all 29 merge commits are his.
  - audio_service: he wrote 579 of 769 (75%). Since 2025 he wrote 17 of 23, and all 11 merge commits are his.
- **Review latency example.** [just_audio PR #1555](https://github.com/ryanheise/just_audio/pull/1555) (2025-09-29, Lennart Enns) is a 4-line Android fix: sync ExoPlayer's shuffle order in `setShuffleOrder`. It is not on the default branch as of 2026-11-19 (fetched via `refs/pull/1555/head`). [Finamp 1.0.3](https://github.com/finamp-app/finamp/blob/1.0.3/pubspec.yaml) depends on a fork of just_audio "until #1555 is merged".
- **Open issues.**
  - audio_service: 186 open ([GitHub issues page](https://www.github.com/ryanheise/audio_service/issues), read 2026-11-19).
  - just_audio: 234 open according to [ecosyste.ms](https://repos.ecosyste.ms/hosts/GitHub/repositories/ryanheise%2Fjust_audio). That is a secondary source, synced about 12 days earlier. GitHub itself was not reachable for just_audio.
  - Recent audio_service Android issues (Jul–Nov 2026) are listed under §6. Titles there are paraphrased; I could not open the individual issues.
- **Alternatives and successors.**
  - No primary source showed a Flutter plugin that wraps Media3's `MediaSessionService`/`MediaLibraryService` with a player.
  - `just_audio_background` is a thin wrapper over audio_service, so it has the same Android backend.
  - `media_kit` 1.2.6 is a libmpv-based player, not a session layer. Its Android audio libs package downloads prebuilt libmpv JARs from GitHub releases at build time ([build.gradle](https://github.com/media-kit/media-kit/blob/main/libs/android/media_kit_libs_android_audio/android/build.gradle)), which F-Droid would remove (see §7).
  - `flutter_media_session` 3.2.1 is a session-only plugin that mentions Media3 notifications ([docs](https://pub.dev/documentation/flutter_media_session/latest)). Its publisher, maturity and implementation are **not verified**.

### Native (Media3)

- **Releases.**
  - 1.8.0 (2025-07-30), 1.9.0 (2025-12-17), 1.10.0 (2026-03-25), 1.11.0 (2026-08-05), 1.11.1 (2026-09-10).
  - 1.12.0-alpha01, alpha02 and beta01 (2026-10-21 to 2026-11-11).
  - Older lines still get patches, for example 1.8.1 (2026-05-20) and 1.9.4 (2026-05-11).
  - Source: [RELEASENOTES.md](https://github.com/androidx/media/blob/release/RELEASENOTES.md) and git tags.
- **People.** 2,325 non-merge commits from 80 authors on `main` in 2026. The `libraries/session` module alone had commits from tonihei (73), bachinger (22), jbibik (19), ibaker (15) and others.
- **Open issue count: not verified.** GitHub was not reachable, and the ecosyste.ms listing for androidx/media is stale (newest issue it shows is #1807, from 2024).

## 2. Android 14/15/16 (and 17) foreground-service compliance

### Platform rules (official docs)

- **Android 14 (target 34+).**
  - Every foreground service must declare a type. For `mediaPlayback` that means the `FOREGROUND_SERVICE_MEDIA_PLAYBACK` permission and the `FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK` constant. There are no runtime prerequisites.
  - A missing type permission throws `SecurityException`.
  - Sources: [FGS types](https://developer.android.com/guide/components/fg-service-types) (updated 2026-11-16) and [FGS changes](https://developer.android.com/develop/background-work/services/fgs/changes) (updated 2026-10-28).
- **Start deadline.** After `startForegroundService()`, the service "has a few seconds" to call `startForeground()`. Otherwise the system throws `ForegroundServiceDidNotStartInTimeException`. The current page gives no exact number ([troubleshooting](https://developer.android.com/develop/background-work/services/fgs/troubleshooting), updated 2026-11-16).
- **Background start (Android 12+).** Starting a foreground service from the background throws `ForegroundServiceStartNotAllowedException` unless an exemption applies. The exemptions include user interaction with a notification or widget, and battery optimisation turned off. **Media button events are not on the documented list** ([restrictions](https://developer.android.com/about/versions/12/foreground-services), updated 2026-11-16).
- **Android 15 (target 35+).** A `mediaPlayback` foreground service may not be launched from a `BOOT_COMPLETED` receiver. `mediaPlayback` has no runtime timeout; the new timeouts apply to `dataSync` and `mediaProcessing`.
- **Android 16 (all apps).** Nothing specific to `mediaPlayback`. Jobs that run alongside a foreground service now count against job quotas, which matters for a WorkManager-based library scan during playback ([Android 16 behavior changes](https://developer.android.com/about/versions/16/behavior-changes-all), updated 2026-10-23).
- **Android 17 (API 37): background audio hardening.** Source: [bg-audio](https://developer.android.com/about/versions/17/changes/bg-audio), updated 2026-10-28.
  - **All apps on 17:** playback, audio focus and volume APIs need a visible activity or a non-`SHORT_SERVICE` foreground service.
  - **Apps targeting 37:** in the background, that foreground service must have while-in-use capability.
  - **Failure mode:** violations fail **silently**, with no exception. Focus requests return `AUDIOFOCUS_REQUEST_FAILED`.
  - **Guidance:** use Media3 `MediaSessionService` ("not likely to be impacted"), or start the `mediaPlayback` foreground service while in the foreground, and "keep the `mediaPlayback` FGS active during transient failures of under 10 minutes."
  - **Testing:** `adb shell cmd audio set-enable-hardening enable|disable|throw`.
  - The page does not say whether Android 17 is stable yet.

### Flutter (audio_service)

- The [README](https://github.com/ryanheise/audio_service/blob/minor/audio_service/README.md#android-setup) manifest lists `WAKE_LOCK`, `FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_MEDIA_PLAYBACK` ("if targeting SDK 34"), the service declared with `foregroundServiceType="mediaPlayback"` and the `MediaBrowserService` intent filter, and a `MEDIA_BUTTON` receiver.
- The README's Android 12 note: by default (`androidStopForegroundOnPause: true`) the service leaves the foreground on pause, so resuming from the background can throw `ForegroundServiceStartNotAllowedException`. The README offers two fixes: set the option to `false`, or ask the user to disable battery optimisation (`optimize_battery` package).
- In [AudioService.java](https://github.com/ryanheise/audio_service/blob/minor/audio_service/android/src/main/java/com/ryanheise/audioservice/AudioService.java), `enterPlayingState()` calls `ContextCompat.startForegroundService(...)` and then `startForeground(...)` straight away. A search of all the plugin's Android sources finds **no handling of `ForegroundServiceStartNotAllowedException`**.
- Nothing in the repo addresses Android 17 audio hardening. **How it behaves there is not verified.**

### Native (Media3)

- `MediaSessionService` creates and updates the media notification and manages the foreground service itself ([background playback](https://developer.android.com/media/media3/session/background-playback)).
- If playback is paused, stopped or failed for more than 10 minutes with no user interaction, the service leaves the foreground. This 10-minute retention arrived in 1.6.0 (2025-03-26) "without risking foreground service restrictions on various devices".
- Foreground-service fixes in recent releases:
  - 1.10.0 detects stale `Intent`s to avoid `ForegroundServiceDidNotStartInTimeException`.
  - 1.11.0 catches `ForegroundServiceStartNotAllowedException` from the asynchronous artwork-load callback and from `stopSelfSafely()`.
  - 1.10.1 propagates that exception across threads.
  - 1.9.0 added a `Context` parameter to `MediaButtonReceiver.onForegroundServiceStartNotAllowedException`.
  - So Media3 does **not** make the background-start restriction go away. It catches the exception and reports it to the app.
- The Android 17 page explicitly recommends Media3 `MediaSessionService`.

## 3. Media resumption and cold start without UI

### Native (Media3): built in, opt-in

Source: [background playback](https://developer.android.com/media/media3/session/background-playback).

- **Off by default.** To opt in, declare `androidx.media3.session.MediaButtonReceiver` and implement `MediaSession.Callback.onPlaybackResumption()`. Declaring the receiver without implementing the callback is not allowed.
- **When it is called.** For resumption requests from Bluetooth and from System UI, "even after the device has been rebooted". At boot it is called with `isForPlayback = false` to build the System UI resumption notification, which should use local title and artwork.
- **System UI resumption card** "is only available if you implement a `MediaLibraryService`".
- **What you still write:** "Your app is responsible for storing the playlist, metadata … and the start position". The future should complete quickly.
- **History:** `MediaButtonReceiver` arrived in 1.1.0 (2023-07-05). `shouldStartForegroundService(Intent)` arrived in 1.5.0 (2024-11-27), so apps can suppress a resumption play without being crashed by the start deadline. The `isForPlayback` parameter arrived in 1.9.0 (2025-12-17).
- **Built in:** service start, foreground promotion, notification, and routing the media button to the callback. **Hand-rolled:** persistence, fast restore, and holding commands that arrive mid-restore.

### Flutter (audio_service)

- 0.18.0 added "Android 11 media session resumption support".
- When the system asks with `EXTRA_RECENT`, `onGetRoot` returns the hard-coded root `"recent"`. Its children come from Dart (`getChildren(AudioService.recentRootId)`).
- A code comment explains the hard-coding: the root "must be given synchronously, and we can't get a synchronous response from the Dart layer".
- **Cold start.**
  - `AudioService.onCreate()` calls `AudioServicePlugin.getFlutterEngine(this)`.
  - If no engine is cached, that constructs a `FlutterEngine` on the main thread and runs the default Dart entrypoint (the app's `main()`), then caches it ([AudioServicePlugin.java](https://github.com/ryanheise/audio_service/blob/minor/audio_service/android/src/main/java/com/ryanheise/audioservice/AudioServicePlugin.java)).
  - So a Bluetooth play press or a resumption request after process death boots the whole Flutter app headlessly, inside the foreground-service start window.
- **Commands during startup.**
  - Java side: session callbacks return early while `listener == null`. `onLoadChildren` returns an empty list in that state.
  - Dart side: 0.18.2 queues platform messages if `AudioService.init()` is called late.
- **Hand-rolled:** persistence, restoring the queue in Dart before answering, and keeping engine boot fast.
- Open issue on exactly this path: an ANR in `AudioService.onCreate()` when `getFlutterEngine()` blocks the main thread during a background start (§6).

## 4. Gapless playback and encoder delay/padding

- **Media3 extractors (source at 1.11.1).**
  - [`GaplessInfoHolder`](https://github.com/androidx/media/blob/1.11.1/libraries/extractor/src/main/java/androidx/media3/extractor/GaplessInfoHolder.java) parses `iTunSMPB` (`com.apple.iTunes` domain) from an ID3 comment or MP4 user data.
  - [`Mp3Extractor`](https://github.com/androidx/media/blob/1.11.1/libraries/extractor/src/main/java/androidx/media3/extractor/mp3/Mp3Extractor.java) falls back to the LAME/Xing header's delay and padding ([`XingFrame`](https://github.com/androidx/media/blob/1.11.1/libraries/extractor/src/main/java/androidx/media3/extractor/mp3/XingFrame.java)) when ID3 has no gapless info. It passes `encoderDelay` and `encoderPadding` into the `Format`, where the audio sink trims them.
- **Recent fixes.**
  - 1.11.0 (2026-08-05): "MP3: Use gapless-aware durations from Xing/Info headers" ([#3183](https://github.com/androidx/media/issues/3183)).
  - 1.11.0: "MP3: Adjust LAME/Xing encoder delay and padding metadata to match decoded PCM trimming" ([#3200](https://github.com/androidx/media/pull/3200)). `XingFrame` now applies a 529-sample offset (`528 + 1`) between the LAME fields and the decoded PCM trim.
  - Gapless playlists stuck in compressed offload mode were fixed in 1.9.3, 1.10.0 and 1.11.0. An offload stall at gapless transitions was fixed in 1.11.1.
- **just_audio.**
  - The README feature table marks gapless as supported on Android. Playlists go through `setAudioSources(...)` since 0.10.0 ([README](https://github.com/ryanheise/just_audio/blob/minor/just_audio/README.md#working-with-gapless-playlists)).
  - Android uses ExoPlayer's `DefaultExtractorsFactory`, so the same extractors, but **at Media3 1.4.1**. That means none of the 2025–2026 MP3 trimming and offload fixes above.
  - Since 0.10.5, offload is off by default. Offload preferences set `setIsGaplessSupportRequired`.
  - **Not verified:** whether forcing a newer Media3 through Gradle dependency resolution works with just_audio 0.10.6.

## 5. Session state for external controllers (notification, lock screen, AVRCP, later Android Auto)

### Native (Media3)

- Session state follows the player automatically. The docs say: "The Media3 library automatically updates the media session using the player's state… you don't need to manually handle the mapping from player to session." They contrast this with the platform session, where you "create and maintain a `PlaybackState` independently" ([control playback](https://developer.android.com/media/media3/session/control-playback), updated 2026-11-10).
- **Buttons and commands.** Notification and controller buttons come from media button preferences (`CommandButton` slots). Commands can differ per controller through `onConnectAsync`. Errors are replicated to the platform session for legacy controllers.
- **Notification on API 33+.** System UI builds the media notification from session data, and `MediaNotification.Provider` customisations only take effect below API 33 ([background playback](https://developer.android.com/media/media3/session/background-playback)).
- **AVRCP.** 1.11.0 fixed "Bluetooth AVRCP browsing didn't recognise `MediaLibraryService` on API 36 and 37".

### Flutter (audio_service)

- The app's `AudioHandler` must broadcast `mediaItem`, `queue` and `playbackState`. A `PlaybackState` carries `controls`, `systemActions`, `androidCompactActionIndices`, `processingState`, `playing`, `updatePosition`, `bufferedPosition`, `speed` and `queueIndex`. The README warns not to broadcast position continuously ([README](https://github.com/ryanheise/audio_service/blob/minor/audio_service/README.md#broadcasting-state-changes)).
- The usual pattern maps just_audio's event streams into these objects in Dart, and the plugin converts them to `MediaSessionCompat`. ExoPlayer's state and the compat session are separate, joined by app code over platform channels.
- **Android Auto** support arrived in 0.18.0 through `MediaBrowserServiceCompat`.

### Reference: Auxio

- Uses `media3-exoplayer` 1.11.1 plus `androidx.media:media:1.8.0` ([app/build.gradle](https://github.com/OxygenCobalt/Auxio/blob/dev/app/build.gradle)). `AuxioService` extends `MediaBrowserServiceCompat`.
- `MediaSessionHolder` is "a component that mirrors the current playback state into the [MediaSessionCompat] and [PlaybackNotification]". Playback state is persisted in its own Room `PersistenceDatabase`.
- **History.**
  - "playback: rearchitecture around media3 (prototype)" (2024-04-07, [04ea683](https://github.com/OxygenCobalt/Auxio/commit/04ea6834fb8c413f3a2101fd081319fa4bd54ad3)).
  - "service: drop media3 session entirely" (2024-08-26, [e43f55b](https://github.com/OxygenCobalt/Auxio/commit/e43f55bc78ee699c3cab7f36f7c6497b14a8e345)).
  - 3.6.0 (2024-10-14): "Moved to raw media session apis rather than media3 session". **No reason is given in the commit or the changelog.**
- 4.1.4 (2026-07-27) fixed the "notification not showing music information… on Android 17". That is the hand-rolled path needing a fix for a new platform version.

## 6. Known issues: UI/session sync after activity destruction or process death

### Flutter (audio_service)

- **Architecture.** Since 0.18.0, UI and handler share one isolate. One `FlutterEngine` is cached in `FlutterEngineCache` and shared by the activity and the service. `disposeFlutterEngine()` skips teardown while any activity is still attached.
- **Recent open Android issues** from the [issues page](https://www.github.com/ryanheise/audio_service/issues) on 2026-11-19. Titles are paraphrased by the fetch tool; I did not open the issues:
  - #1165 (2026-07-26): ANR in `AudioService.onCreate()` when `getFlutterEngine()` blocks the main thread during a background service start.
  - #1176 (2026-11-01): media session commands dropped after the service is recreated while the engine stays alive.
  - #1179 (2026-11-03): a deep link in the launch intent is ignored when the service has already started the engine.
  - #1180 (2026-11-06): disposing the engine destroys the cached engine, leading to a second engine, a blank screen and an ANR on Pixel 10.
  - #1181 (2026-11-06): play/pause media keys behave as a toggle, so pause can start playback.
  - #1174 (2026-10-31): on Android TV 14–16 the "Now Playing" card's `PendingIntent` is blocked by background-activity-launch rules.

### Native (Media3)

- **How the UI connects.** It builds a `MediaController` asynchronously from a `SessionToken`, typically in `onStart`, and releases it in `onStop`. Pending commands are still delivered before unbinding. The controller is a `Player`, observed with `Player.Listener`, and `MediaController.Listener.onDisconnected` reports a lost session ([connect to a media app](https://developer.android.com/media/media3/session/connect-to-media-app), updated 2026-10-28).
- **Recent session fixes.**
  - 1.11.1: an NPE when an in-process controller is released from a `Player.Listener` callback ([#3375](https://github.com/androidx/media/issues/3375)), and a main-thread deadlock when a legacy `MediaBrowser` connects while `onGetLibraryRoot()` answers asynchronously ([#3393](https://github.com/androidx/media/issues/3393)).
  - 1.11.0: `PositionInfo` lost its Timeline UIDs on the controller.
  - 1.12.0-alpha01: `getControllerForCurrentRequest()` returned null during play requests on API 31/32 before the service was in the foreground.
- **Not verified:** the open-issue backlog in this area. GitHub could not be queried.

## 7. F-Droid buildability

- **Flutter app with these plugins: yes, shown by a real app.** [Finamp 1.0.3](https://f-droid.org/en/packages/com.unicornsonlsd.finamp/) (added 2026-11-11, built and signed by F-Droid) uses audio_service ^0.18.18 and a just_audio fork. Its [recipe](https://github.com/f-droid/fdroiddata/blob/master/metadata/com.unicornsonlsd.finamp.yml) (read from the GitHub mirror of [fdroiddata](https://gitlab.com/fdroid/fdroiddata)):
  - uses `srclibs: flutter@stable`, a plain git clone of flutter/flutter ([srclibs/flutter.yml](https://github.com/f-droid/fdroiddata/blob/master/srclibs/flutter.yml));
  - checks out the version in `.flutter-version` and runs `flutter pub get --enforce-lockfile`;
  - sets `scandelete: .pub-cache`;
  - rebuilds the native `isar` library from source with Rust;
  - runs `flutter build apk --release`.
  - There are no steps specific to just_audio or audio_service.
- **Engine artifacts.** The Flutter SDK srclib downloads prebuilt engine artifacts at build time. A 2025-08-18 F-Droid build log of another Flutter app shows the engine download ([vernet log](https://monitor.f-droid.org/builds/log/org.fsociety.vernet/38)). The download host is not shown in the log.
- **Play Core references.**
  - Flutter 3.50.0's embedding still contains `PlayStoreDeferredComponentManager`, which imports `com.google.android.play.core.splitinstall.*` ([source](https://github.com/flutter/flutter/blob/3.50.0/engine/src/flutter/shell/platform/android/io/flutter/embedding/engine/deferredcomponents/PlayStoreDeferredComponentManager.java)).
  - In 2023, [fdroiddata#2949](https://gitlab.com/fdroid/fdroiddata/-/issues/2949) reported 6 Play Core classes found in an empty Flutter app's release APK, with no resolution recorded.
  - **Not verified:** whether the scanner flags this today. Finamp's 2026 recipe has no workaround for it and builds.
- **Reproducible builds.**
  - F-Droid's [docs](https://f-droid.org/en/docs/Reproducible_Builds/) name Flutter among the frameworks where embedded build paths break reproducibility. The fix is to build in the same path (and `flutter config --android-sdk` if the SDK path is embedded).
  - A [2024 forum case](https://forum.f-droid.org/t/flutter-app-not-reproducible/27462) (differing `libapp.so`) was solved by matching the CI build path.
  - Finamp is F-Droid-signed, not reproducible or developer-signed.
- **Prebuilt binaries in pub packages** are removed by scandelete, and exempting them is "not allowed per F-Droid policy". The fix is to build them from source as a srclib ([forum, 2025-05-28](https://forum.f-droid.org/t/correct-fix-for-scandeleted-binaries-in-dependency/32256)). This would hit `media_kit`'s libmpv JARs, but not just_audio or audio_service, which are pure Java plus Dart.
- **Media3 / Kotlin.** [Auxio 4.1.5](https://github.com/f-droid/fdroiddata/blob/master/metadata/org.oxycblt.auxio.yml) is built by F-Droid with `gradle: yes`.
  - Auxio vendors a Media3 fork as a git submodule, included with `includeMedia3` ([settings.gradle](https://github.com/OxygenCobalt/Auxio/blob/dev/settings.gradle)), to get the FFmpeg decoder.
  - Its recipe deletes lines matching `gms` from `media/build.gradle`, drops the `foojay` plugin, and scandeletes `media/libraries`.
  - Its other androidx dependencies resolve from the `google()` Maven repo.
  - An app using plain Maven `media3-exoplayer`/`media3-session` without FFmpeg would not need the vendoring. That was not tested here.

## 8. INTERNET permission check

| Source | Declares | Notes |
|---|---|---|
| Flutter app template, `src/main` | nothing | [template](https://github.com/flutter/flutter/blob/stable/packages/flutter_tools/templates/app/android.tmpl/app/src/main/AndroidManifest.xml.tmpl) |
| Flutter app template, `src/debug` and `src/profile` | **INTERNET** | "required for development… breakpoints… hot reload" ([debug](https://github.com/flutter/flutter/blob/stable/packages/flutter_tools/templates/app/android.tmpl/app/src/debug/AndroidManifest.xml.tmpl)) |
| just_audio, audio_service, audio_session (Android manifests) | nothing | read from default branches |
| Media3 `common`, `exoplayer` (1.4.1 and 1.11.1) | `ACCESS_NETWORK_STATE` (+ `WAKE_LOCK` in exoplayer 1.11.1) | no Media3 library manifest declares INTERNET at either tag |
| Auxio app manifest | removes `ACCESS_NETWORK_STATE` | `tools:node="remove"` with the comment "Work around ExoPlayer requiring network permissions we do not use" ([manifest](https://github.com/OxygenCobalt/Auxio/blob/dev/app/src/main/AndroidManifest.xml)) |

- just_audio's local HTTP proxy serves `StreamAudioSource`, `LockCachingAudioSource` and proxied request headers. It runs a `localhost` HTTP server, which the README says needs cleartext access ([README](https://github.com/ryanheise/just_audio/blob/minor/just_audio/README.md)). On Android, opening any socket, loopback included, requires INTERNET. That is general platform knowledge and was not re-verified here. Playing files with `AudioSource.file`/`uri` does not use the proxy.
- ExoPlayer adds `ACCESS_NETWORK_STATE` on both stacks, because just_audio brings in `media3-exoplayer`.
- **Not done:** building a release APK of either stack and dumping its merged permissions. That is the check to run before locking the stack.

---

## Implications for the stack decision

Facts and trade-offs only. The decision belongs to "Stack: Flutter or Kotlin + Media3?".

- **The playback engine is the same; the session layer and engine version differ.**
  - Both stacks play audio through Media3 ExoPlayer.
  - Flutter ships ExoPlayer at 1.4.1 (2024-08-23) under a session layer built on legacy `androidx.media` 1.7.0, with no Media3 migration branch. The version moves only when the single upstream maintainer bumps it.
  - Native ships whatever Media3 version you choose. Today that means getting the 2026 MP3 delay/padding fixes.
- **Kotlin + Media3 is really two options:**
  - (a) Media3's own session layer: foreground service, notification, resumption routing and player-to-session state mapping are built in, and the Android 17 docs endorse it;
  - (b) Auxio's approach: Media3 ExoPlayer under a hand-written `MediaSessionCompat`/`MediaBrowserServiceCompat`, with its own state mirroring and persistence. Auxio left Media3's session layer in 2024 without saying why, and later needed an Android 17 notification fix.
  - The reference code you plan to copy for the hard parts follows (b).
- **Cold start path.** On Flutter, a headset button or resumption request after process death boots a FlutterEngine and the app's `main()` on the service's main thread. That is the path the map's "holding commands mid-restore" problem lives on. audio_service has open 2026 issues on exactly that path (ANR in `onCreate`, commands dropped after service recreation). On Media3, `onPlaybackResumption` runs in plain Kotlin with no engine boot.
- **Who handles foreground-service edge cases.**
  - Media3 retains the foreground service for 10 minutes after pause and catches or reports `ForegroundServiceStartNotAllowedException`, which matches Google's Android 17 guidance.
  - audio_service leaves the foreground on pause by default, leaves the exception to the app, and says nothing about Android 17. Its Android 17 behaviour is unverified.
- **Maintenance risk.**
  - Flutter: two critical plugins with a bus factor of one, one build-tooling release each in 2026, and a small Android fix waiting 13+ months. A flagship F-Droid app (Finamp) ships a fork.
  - Media3: a large Google team releasing every 3–5 months. Its API surface moves too: deprecations and breaking changes on "unstable" APIs show up in its release notes.
- **F-Droid is feasible on both.**
  - Flutter adds the SDK srclib, the engine artifact download, the Play Core reference question (unverified) and build-path reproducibility work.
  - Media3 is a normal Gradle build. Vendoring is only needed for the FFmpeg extension.
- **INTERNET.**
  - Neither stack's libraries declare INTERNET.
  - On Flutter, debug and profile builds carry INTERNET by design (tooling), so "never INTERNET" applies to release builds only. just_audio's proxy-based sources must be avoided.
  - On both stacks ExoPlayer adds `ACCESS_NETWORK_STATE`, which can be removed in the manifest as Auxio does.
- **Not verified (could change the picture):**
  - pub.dev publish dates beyond the git tags;
  - the content of individual audio_service issues;
  - Media3's open-issue count;
  - whether a just_audio app can safely force a newer Media3;
  - whether the F-Droid scanner flags Flutter's Play Core references in 2026;
  - Android 17's stable status;
  - audio_service's behaviour under Android 17 audio hardening;
  - merged release-APK permissions for both stacks.
