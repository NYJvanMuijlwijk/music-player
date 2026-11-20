# Storage: Songs, Queues and playback state

Decided in issue #9 ("Storage: database and schema for Queues and playback state"). Terms follow `CONTEXT.md`. Builds on ADR 0003 (Songs have their own identity) and the Queue model (#6), Playback architecture (#8) and Testing (#15) decisions.

## Overview

- **One Room database** in the app's private storage holds Songs, Queues and saved playback state. Use the stable Room line (2.8 today); move to Room 3 only if it's stable when the build starts.
- **App settings** (the Library folders) live outside it, in Jetpack DataStore.
- **The Song table is the Library** for the whole app: the song, album, artist, folder and search screens read it, never MediaStore live (ADR 0004).
- Times are milliseconds since 1970 (UTC).

## `song`: every Song in the Library, plus Missing songs that are still in a Queue

| Column | Type | Notes |
|---|---|---|
| `id` | integer, primary key | Assigned by the app, never reused (`AUTOINCREMENT`) |
| `media_store_id` | integer, nullable, unique | The current file's MediaStore `_id`, a cache of where to play from. **Null means Missing song** |
| `missing_since` | integer, nullable | Set when the Song loses its file, cleared when it's relinked. Null exactly when `media_store_id` isn't |
| `volume` | text | Last known path: storage volume |
| `relative_path` | text | Last known path: folder, as MediaStore's `RELATIVE_PATH` |
| `file_name` | text | Last known path: file name. Unique together with the two above |
| `format` | text | MIME type, for the duplicate tie-break ("same format") |
| `flac_audio_md5` | blob, nullable | From FLAC STREAMINFO. Null for non-FLAC or an all-zero MD5 |
| `title`, `album`, `album_artist`, `artist` | text, nullable | Tags |
| `track_number`, `disc_number`, `year` | integer, nullable | Tags |
| `duration_ms` | integer | |
| `file_modified` | integer | MediaStore `DATE_MODIFIED` when tags and MD5 were last read, so a sync can skip unchanged files |
| `cover_source`, `cover_key`, `cover_modified` | text, text, integer, all nullable | Where the Song's Cover comes from and a hash of the picture. See `covers.md` |

Indexes: `media_store_id`; path (unique); `flac_audio_md5`; `album_artist, album`; `artist`; `title`. These cover browsing by album, artist, folder and song, plain text search, and the Library sync's matching steps.

Albums and artists aren't tables: they're grouped from the tags. An album is the pair (album artist, or artist when that's empty, plus album).

## `queue`: one row per Queue, including what it remembers

| Column | Type | Notes |
|---|---|---|
| `id` | integer, primary key | Never reused |
| `name` | text | |
| `auto_named` | boolean | Cleared on rename |
| `source_type` | text | `album`, `artist`, `folder`, `all_songs`, `search`, or `none` (for example, a Queue made by "Add to other Queue... > New Queue") |
| `source_key` | text, nullable | Which album, artist, folder or search query |
| `source_unchanged` | boolean | Drives the same-source rule (below). Cleared by any edit to the entries |
| `pinned` | boolean | |
| `shuffle` | boolean | |
| `current_entry_id` | integer, nullable | The entry that is playing or paused. Points at `queue_entry`; becomes null if that entry is deleted |
| `position_ms` | integer | Position in the current Song |
| `created_at` | integer | |
| `last_played_at` | integer | Drives cleanup: least recently played unpinned Queue goes first |

## `queue_entry`: one row per entry in a Queue

| Column | Type | Notes |
|---|---|---|
| `id` | integer, primary key | Own id, so the same Song can be in a Queue twice |
| `queue_id` | integer | Points at `queue`. Deleting the Queue deletes its entries |
| `song_id` | integer | Points at `song`. A Song can't be deleted while an entry points at it |
| `queue_order` | integer | 0 to n−1, the Queue's own order |
| `play_order` | integer, nullable | 0 to n−1 while Shuffle is on, null while it's off |

Indexes: `queue_id, queue_order`; `queue_id, play_order`; `song_id` (for "is this Song in any Queue?" and relinking).

Missing songs keep their entries and numbers. The list handed to the player skips them.

## `playback_state`: a single row

| Column | Type | Notes |
|---|---|---|
| `active_queue_id` | integer, nullable | Points at `queue`. Null means there is no Active Queue, so a cold start does nothing (as decided in "Playback architecture") |

## `library_sync_state`: one row per storage volume

| Column | Type | Notes |
|---|---|---|
| `volume` | text, primary key | |
| `media_store_version` | text | `MediaStore.getVersion()`. If it changes, the next sync compares every file instead of only the changed ones |
| `generation` | integer | Last MediaStore generation the sync has handled, so the next sync only reads newer changes |

It lives in the database, not in DataStore, so a sync's Song changes and its "handled up to here" mark are saved in the same transaction.

## Missing songs

A Song is Missing when it has no current file: `media_store_id` is null and `missing_since` is set. The mark is on the Song, never on a Queue entry, so a Song is Missing in every Queue at once and relinked in every Queue at once. It keeps its last known path, tags, duration and FLAC MD5, which is what a Library sync uses to find it again. A Song with no file that is in no Queue is deleted at the next sync.

## Queue order and Play order

Each entry carries both numbers. With Shuffle on, `play_order` is the order it plays in; with Shuffle off it's null and the Queue plays in `queue_order`.

- **Play next:** right after the current Song in both orders, so it still plays next if Shuffle is then turned off.
- **Add to queue, Move/Copy to Queue:** last in both orders.
- **Drag while shuffled:** changes `play_order` only. **Drag while not shuffled:** changes `queue_order` only.
- **Remove:** delete the row and close the gap in both orders.
- **Shuffle on, or the Queue starting over while shuffled:** write a fresh `play_order` with the current Song first.
- **Shuffle off:** clear `play_order`. Turning it on again makes a fresh shuffle; the old one is not restored.
- **Missing songs** keep their numbers. Only the list handed to the player leaves them out.

## Same-source rule

A tap in an album, artist or folder jumps within the Active Queue instead of starting a new one when the Active Queue has the same `source_type` and `source_key`, `source_unchanged` is still true, and the tapped Song is in it.

- Any edit to the entries clears `source_unchanged`: add, remove, move, Play next.
- Turning Shuffle on or off, skipping and playing don't.
- A Library change doesn't either, but if the tapped Song isn't in the Queue (the album gained a Song since), the tap starts a new Queue.

## Deleting Queues

A deleted Queue is gone for good; there is no trash. A manual delete offers a few seconds of "Undo", held in memory only. Cleanup past 20 unpinned Queues stays silent. Deleting the Active Queue, by hand or by removing the last Song of an unpinned one, stops playback and leaves no Active Queue until something is played. A pinned Active Queue whose last Song is removed stays active and empty, with playback stopped.

## Migrations

- Room's exported schema JSON is committed to the repo (`schemas/`).
- Before daily use starts, schema version 1 may change freely. After that, every schema change is a migration: Room's automatic migration where it can generate one, a hand-written one where it can't. Each migration gets a test.
- Never `fallbackToDestructiveMigration` in any form: losing Queues is never an acceptable upgrade path.
- At build time, check whether Room's migration tests can run as plain JVM tests. If they can't, migration tests are the one exception to "no instrumented tests in v1".

## Backup

Cloud backup is off; device-to-device transfer is on (`dataExtractionRules` for Android 12+, `fullBackupContent` for Android 11). Queues follow the user to a new phone, and their Songs relink by path once the Library folders are synced there. Nothing goes to Google's servers.

## Rules the code keeps

- `queue_order` and `play_order` are always 0 to n−1 with no gaps, rewritten in one transaction per edit.
- Each write that belongs together is one transaction: switching Queues (outgoing Queue's position, incoming Queue becomes active), a Queue edit, one Library sync batch.
- The rest of the app goes through one Queue store interface, never Room directly. Restore and save logic is tested on the JVM against a fake of that interface (per "Testing playback kill and restore").
