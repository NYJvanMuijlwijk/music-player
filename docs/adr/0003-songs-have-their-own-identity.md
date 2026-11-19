# Songs have their own identity, not MediaStore's `_id`

The app keeps its own table of Songs, each with a stable id that the app assigns, and Queue entries point at that id. A Library sync matches MediaStore's audio rows to Songs using what each Song remembers about its file: path, FLAC audio MD5, tags and duration. MediaStore's `_id` is stored only as a cache of the Song's current file, never as its identity.

The library arrives through Syncthing, which replaces a file instead of editing it. Testing on the phone (issue #10) showed that a move always gives the file a new `_id`, and a retag often does. Even when `_id` survives, `generation_added` is bumped as if the Song were new. During a replace, the row is missing from the audio table for up to about 15 s. A Queue keyed on `_id` would lose Songs on every retag or reorganisation done on the PC.

Matching happens once per sync, not once per Queue entry. A Song that comes back is relinked everywhere at once, and a Song stays the same Song in every Queue while its file moves.

## Considered Options

- **MediaStore `_id`**: rejected. It isn't stable under Syncthing replaces (issue #10).
- **Path only**: rejected. A move or rename breaks it.
- **Hash of tags only** (Auxio's approach): rejected. A retag breaks it.
- **MusicBrainz track ID**: rejected. None of the 941 Songs carry one (issue #4).
- **Lookup keys stored in each Queue entry**: rejected. Every Queue would repeat the matching, and two Queues could resolve the same file differently.
