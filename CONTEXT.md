# Music Player

An offline Android music player for a locally stored music collection, built around multiple Queues that are never silently emptied.

## Language

**Library**:
All songs on the device that Android's media index exposes to the player.
_Avoid_: Collection, database, catalog

**Song**:
One playable audio file in the Library.
_Avoid_: Track, file, item

**Queue**:
A named, ordered list of Songs with its own playback position. Several Queues exist side by side; playing something new from the Library starts a new one.
_Avoid_: Playlist, play queue, now playing

**Active Queue**:
The one Queue currently loaded for playback. It is the only Queue that controls outside the app (notification, headset, lock screen) can see or act on; switching to another Queue makes that one active.
_Avoid_: Current queue, playing queue, now playing

**Pinned Queue**:
A Queue the user has marked to keep, exempt from automatic cleanup.
_Avoid_: Saved queue, favourite queue

**Missing song**:
A Song in a Queue whose file can't currently be found in the Library. It stays in the Queue, marked, until the user removes it or it is found again.
_Avoid_: Broken song, dead entry, unavailable track
