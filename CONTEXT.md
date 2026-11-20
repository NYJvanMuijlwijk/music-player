# Music Player

An offline Android music player for a locally stored music collection, built around multiple Queues that are never silently emptied.

## Language

**Library**:
All songs in the Library folders that Android's media index exposes to the player.
_Avoid_: Collection, database, catalog

**Library folder**:
A folder the user has chosen to make part of the Library, including its subfolders, on every storage volume. By default the only one is `Music/`. Removing one turns its Songs in Queues into Missing songs.
_Avoid_: Source, scan folder, include folder

**Song**:
One piece of music in the Library, played from one audio file. It keeps its identity when its file is moved or retagged, so Queues keep pointing at it.
_Avoid_: Track, file, item

**Artist**:
A name in the artist tags of the Library's Songs. Names that differ only in letter case are the same Artist. A Song credited to "X feat. Y" belongs to the Artist "X feat. Y".
_Avoid_: Performer, band

**Album**:
The Songs that share an album name and an album artist (or, without one, an artist), ignoring letter case. Two albums with the same name by different artists are different Albums.
_Avoid_: Record, release, disc

**Cover**:
The picture shown for a Song: the image file in its folder, or else the picture embedded in its file. An album shows the Cover of its first Song.
_Avoid_: Artwork, album art, thumbnail

**Folder access**:
The user's one-time permission for the app to read every file in a Library folder, which the music permission doesn't cover. Covers and lyrics files are read through it.
_Avoid_: Folder grant, storage permission, SAF access

**Library sync**:
Matching what Android's media index currently lists to the Songs the app already knows, run at start and whenever the index changes. Files that are moved or retagged stay the same Song. A Song whose file is gone becomes a Missing song, and a Missing song whose file comes back is relinked.
_Avoid_: Scan, rescan, refresh, import

**Queue**:
A named, ordered list of Songs that remembers its own current Song, position in that Song and Shuffle. When it reaches its end it starts again from the top, reshuffled if Shuffle is on. Several Queues exist side by side; playing something new from the Library starts a new one.
_Avoid_: Playlist, play queue, now playing

**Active Queue**:
The one Queue currently loaded for playback. It is the only Queue that controls outside the app (notification, headset, lock screen) can see or act on; switching to another Queue makes that one active.
_Avoid_: Current queue, playing queue, now playing

**Pinned Queue**:
A Queue the user has marked to keep, exempt from automatic cleanup. Unpinned Queues are cleaned up, least recently played first, once there would be more than 20 of them; the Active Queue never is.
_Avoid_: Saved queue, favourite queue

**Play order**:
The order a Queue actually plays in. The same as the Queue's own order unless Shuffle is on.
_Avoid_: Shuffle order, playback order

**Shuffle**:
An on/off play mode of each Queue: it plays through a shuffled Play order without changing the Queue's own order, and turning it off goes back to that order.
_Avoid_: Random, mix, shuffle mode

**Missing song**:
A Song in a Queue whose file can't currently be found in the Library. It stays in the Queue, marked, until the user removes it or it is found again.
_Avoid_: Broken song, dead entry, unavailable track
