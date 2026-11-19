# The Song table is the Library for the whole app

The app's own Song table, in one Room database alongside Queues and saved playback state, is what every screen browses and searches: songs, albums, artists, folders and search results all come from it. MediaStore is read only by the Library sync, which keeps the Song table in step with it. Albums and artists are grouped from the Songs' tags, with no album or artist tables.

After ADR 0003, every file in the Library already has a Song row, so the table is a complete copy of the Library. Browsing from it means a tap always has a Song id to start a Queue with, the screens and the Queues can never disagree about what a Song is, and a Missing song never turns up in browsing. Room is chosen because it is Android's own SQLite layer, gives the UI live updates, and generates and tests migrations, so Queues survive every upgrade.

## Considered Options

- **Query MediaStore live for browsing**: rejected. Each tap would need to be matched back to a Song before it could join a Queue, and a Song would vanish from the screens for up to about 15 s during every Syncthing replace, which the Library sync's 30 s wait hides.
- **SQLDelight**: rejected. Workable, but Room's generated migrations and live queries cover what v1 needs with less hand-written SQL.
- **JSON files per Queue**: rejected. No transactions across Queues, Songs and playback state, and no way for the Library sync to ask which Songs are in any Queue.
- **A separate store for playback state**: rejected. It's a few columns per Queue plus one "which Queue is active" row, and switching Queues must save both sides in one transaction.
