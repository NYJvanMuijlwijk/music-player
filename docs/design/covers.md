# Covers

Decided in issue #20 ("Artwork: embedded pictures, folder images and caching"). Terms follow `CONTEXT.md`. Builds on the v1 cut (#18, lyrics through a folder grant), Screens and navigation (#19), Storage (#9, `storage.md`) and Song identity (#5, ADR 0003). No online covers, ever.

## Where Covers show

- **Large:** Player, the album page header.
- **Medium:** the Albums grid, the row of albums on an artist page, album results in Search, the Active Queue card on the Queues tab.
- **Small:** the now-playing strip, and the start of every song row in the Songs tab, Queue rows and song results in Search.
- **Not shown:** album page tracks (they keep their track numbers), the Artists list and the Folders list. Artists get no photos, because there is no offline source for them.
- **Outside the app:** the notification, lock screen, resume card and Bluetooth or car displays show the current Song's Cover, the same picture as Player. There is no setting to hide it.
- **No Cover:** one neutral tile with a music note, in the theme colours.
- **Missing songs:** that same tile, greyed with the rest of the row.
- **Small pictures** are scaled up to fill Player. Many of the library's older covers are 200×200 and look soft there. 1000×1000 is the target for new and upgraded covers.

## Changes to the Screens decisions (#19)

- **Queue rows:** drag handle on the left, then the Cover, title and artist, then ⋮. No row numbers; the "3 of 10" chip says where you are. The playing Song shows a playing indicator over its Cover. Songs tab and Search rows look the same without the handle.
- **First run:** welcome, Android's music permission, then Folder access on the Library folder (`Music/` by default), explained as "covers and lyrics", then "Reading your Library". This replaces the dialog that asked the first time lyrics were opened.
- **Settings:** "Lyrics folder access" becomes **Folder access**, for covers and lyrics. Adding a Library folder asks for its Folder access right then.
- **Folder access declined:** Covers come from embedded pictures only and lyrics from tags only, until it is allowed in Settings.

## Which picture is a Song's Cover

1. **The folder image**, found by the rule below.
2. **Else the picture embedded in the Song's file.**
3. **Else none**, and the placeholder tile shows.

**Folder image rule.** Look in the Song's own folder. If that folder is a disc folder (`CD1`, `Disc 2` and the like), look in its parent too, never further and never above the Library folder. Take the first match:

1. an image whose name contains the album name, like `Artist - Album.jpg`;
2. an image named `cover`, `folder`, `front` or `album`;
3. the only image in the folder.

Names match in any case; images are `.jpg`, `.jpeg`, `.png` or `.webp`. If nothing matches, the Song has no folder image.

**An album's Cover** (grid, album page, artist page, Search) is the Cover of its first Song, in disc and track order.

## How the app reads them

- **Folder images go through Folder access:** an `ACTION_OPEN_DOCUMENT_TREE` grant on each Library folder, read with document URIs (not file paths). It is the same grant the lyrics use.
  - Not `READ_MEDIA_IMAGES`: MediaStore indexes `folder.jpg` and `AlbumArt*.jpg` as non-media, so no media permission can open them, and on Android 14+ the request offers "Select photos".
  - Not `READ_MEDIA_AUDIO` alone: it cannot open or even list the images in an album folder.
  - Not Android's own audio thumbnails (`ContentResolver.loadThumbnail`): they are capped near half the screen width, prefer any `.jpg` over the right file, don't refresh when only the image changes, and are cached in `Music/.thumbnails`, inside the Syncthing folder.
- **Embedded pictures:** the Library sync spots a FLAC `PICTURE` block while it reads the header it already reads for the audio MD5, without loading the picture. The few MP3 and M4A files use `MediaMetadataRetriever` (or Media3's `MetadataRetriever`).

## Storage

Three columns join the `song` table (see `storage.md`):

| Column | Type | Notes |
|---|---|---|
| `cover_source` | text, nullable | Where the Cover comes from: the folder image's document id, `embedded`, or null for none |
| `cover_key` | text, nullable | A hash of the picture's bytes. Names the small copy and keys the in-memory image cache, so it changes whenever the picture does |
| `cover_modified` | integer, nullable | The folder image's last-modified time, for the start-up re-check. Null for embedded or none |

- **Small copies:** one JPEG of about 500 px per distinct `cover_key`, made once and kept in the app's cache folder (`cacheDir/covers/`). Never scaled up. An album's tracks share one copy, about 30 MB for the current library. A sync deletes copies no Song points at. If Android clears the cache, copies are rebuilt as they're needed.
- **Which size where:** rows, the grid, the strip and the artist page use the small copy. Player, the album page header and the media session read the original picture, scaled to fit.

## When Covers change

- **A changed embedded picture** changes the audio file, so the Library sync it triggers re-reads the Cover and gets a new `cover_key`.
- **A replaced folder image on its own** doesn't trigger a sync, because syncs follow audio changes. So each app start re-checks every folder's chosen image (its last-modified time, and whether a better-ranked image appeared), and a new picture shows then.
- **No refresh button in v1.** Android's App info › Clear cache is the escape hatch. A manual cover refresh is a later feature.

## Covers outside the app

- **The media session** gets each Song's `artworkUri` pointing at a small content provider of the app's own, which serves the original picture. The provider is not exported, so other apps never see the covers. System UI then can't open the URI itself and falls back to the session's bitmap, which Media3 always sets. Setting `artworkUri` also replaces the embedded picture ExoPlayer would otherwise pass on. Never use `artworkData` on Queue or browse items: Media3 decodes it for every item.
- **Sizes:** the platform caps session art at 320dp; Bluetooth (AVRCP 1.6+) gets 200×200.
- **Software bitmaps** for the session. Media3's default loader already makes them. A Coil-based loader must turn hardware bitmaps off; Auxio reports that they crash Android 17's media session.
- **The resume card** after a reboot: the one item `onPlaybackResumption` returns carries the small copy's bytes as `artworkData`.

## Loading in the UI

- **Coil 3**, core and Compose only, with no network artifact. A custom `Fetcher` and `Keyer` load a Song's Cover keyed by `cover_key` and size. Coil's own disk cache stays off; the small copies are the disk cache.
- **The build checks** that the merged manifest has no `INTERNET` permission.
- **Reference code:** Auxio (GPL-3.0, copied with its notice kept per ADR 0002): `musikr/.../covers/` (`StoredCovers`, `FSCovers`, `Transcoding`), `app/.../image/coil/CoverFetcher.kt` and `MediaSessionHolder.kt`.

## Facts this rests on

Checked on 2026-11-20 against the Android 17 source (LineageOS `lineage-24.0`, pinned to `android-17.0.0_r1`), Media3 1.11.1, Auxio `dev` and Coil 3.6.3. Not yet checked on the phone itself.

- MediaStore's album-art name pattern (`folder.jpg`, `AlbumArt*.jpg` → non-media): [`FileUtils.java`](https://raw.githubusercontent.com/LineageOS/android_packages_providers_MediaProvider/lineage-24.0/src/com/android/providers/media/util/FileUtils.java), applied in `ModernMediaScanner.resolveMediaTypeFromFilePath`.
- Which rows each media permission can read: [`AccessChecker.java`](https://raw.githubusercontent.com/LineageOS/android_packages_providers_MediaProvider/lineage-24.0/src/com/android/providers/media/AccessChecker.java).
- Partial photo access on Android 14+: [developer.android.com](https://developer.android.com/about/versions/14/changes/partial-photo-video-access).
- A tree grant reads every file under it: [developer.android.com](https://developer.android.com/training/data-storage/shared/documents-files).
- Platform audio thumbnails (embedded, then the folder's best `.jpg`, half the screen width, `Music/.thumbnails`): [`ThumbnailUtils.java`](https://raw.githubusercontent.com/LineageOS/android_frameworks_base/lineage-24.0/media/java/android/media/ThumbnailUtils.java) and [`MediaProvider.java`](https://raw.githubusercontent.com/LineageOS/android_packages_providers_MediaProvider/lineage-24.0/src/com/android/providers/media/MediaProvider.java).
- System UI loads the art URI, then falls back to the session bitmap: [`MediaDataLoader.kt`](https://raw.githubusercontent.com/LineageOS/android_frameworks_base/lineage-24.0/packages/SystemUI/src/com/android/systemui/media/controls/domain/pipeline/MediaDataLoader.kt).
- FLAC `PICTURE` block layout: [RFC 9639](https://www.rfc-editor.org/rfc/rfc9639.html), sections 8.1 and 8.8.
- Media3 artwork handling (`BitmapLoader`, `artworkUri` replacing embedded art, queue decoding): [androidx/media](https://github.com/androidx/media), `release` branch.

To check when building: the phone's real session-art size (Samsung may differ), that System UI falls back to the bitmap for a non-exported provider, how long Folder access takes to list about 570 folders, and that Coil adds no `INTERNET`.
