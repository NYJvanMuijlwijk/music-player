# Kotlin + Media3 + Compose instead of Flutter

The player is native Kotlin with Jetpack Media3 (ExoPlayer plus Media3's own `MediaLibraryService` session) and Compose, even though Flutter is the author's main stack. In a music player the hard part is the playback service: foreground-service rules, cold start from a headset button or the system resume card after process death, and keeping the session state correct for every outside controller. Media3 builds all of that in and is Google's documented path for Android 17's audio hardening. Flutter's `audio_service` + `just_audio` rebuild it by hand, cold-start a FlutterEngine inside the service's `onCreate`, pin Media3 1.4.1 (missing the 2026 MP3 gapless fixes), and depend on a single maintainer. Flutter speed only helps with the UI, which is the easy part.

## Considered Options

- **Flutter (`just_audio` + `audio_service`)**: rejected for the reasons above. See the research in "Flutter audio stack vs Media3: current state" (issue #2).
- **Hybrid: Flutter UI over a native Media3 service**: rejected. It needs two languages, two build systems and a hand-written bridge for every command and state stream, and the UI/session sync bugs move into that bridge.
- **Auxio's approach: ExoPlayer under a hand-written `MediaSessionCompat`**: rejected. It means rebuilding the session state mapping and foreground-service handling that Media3 provides. Auxio is still the reference for ExoPlayer setup, MediaStore and saving playback state, but not for the session layer.
