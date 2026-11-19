#!/usr/bin/env python3
"""Compare the music files on an Android phone with what MediaStore indexes.

Collects the facts for the wayfinder task "Check MediaStore against your
library": file counts per format, MediaStore counts, files MediaStore misses
and the likely reason, tag quality, MusicBrainz tags on a sample, and likely
duplicates. Writes a Markdown report to paste into the ticket.

Usage:
    python3 check_mediastore.py [MUSIC_DIR ...] [--sample N] [--local-copy DIR]

MUSIC_DIR defaults to Music/ on internal storage and on every SD card. Pass
folders explicitly if your music lives elsewhere (/sdcard/... is fine).

Needs adb (Arch: android-tools) with the phone connected and USB debugging
allowed. ffprobe (Arch: ffmpeg) is optional and used for the tag sample.
Read-only on the phone: it lists files, queries MediaStore and pulls copies
of the sampled files into a temporary folder that is deleted afterwards.
"""

import argparse
import collections
import concurrent.futures
import json
import os
import random
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path, PurePosixPath

# v1 plays through the platform decoders only: MP3, AAC, FLAC, Opus, Vorbis.
V1_EXTS = {"mp3", "aac", "m4a", "flac", "opus", "ogg", "oga"}
V1_CODECS = {"mp3", "aac", "flac", "opus", "vorbis"}
OTHER_AUDIO_EXTS = {
    "wav", "wave", "aif", "aiff", "aifc", "alac", "ape", "wma", "wv", "dsf",
    "dff", "mpc", "tta", "tak", "ac3", "eac3", "dts", "mka", "mp4", "m4b",
    "3gp", "amr", "awb", "mid", "midi", "caf", "au", "ra", "spx", "mp2",
    "weba", "webm",
}
AUDIO_EXTS = V1_EXTS | OTHER_AUDIO_EXTS
# Containers that can hold more than one codec: probe a few of each.
MULTI_CODEC_EXTS = {"m4a", "mp4", "ogg", "oga", "mka"}

MS_URI = "content://media/external/audio/media"
MS_COLUMNS = ["_id", "_data", "mime_type", "is_music", "title", "artist",
              "album", "album_artist", "track", "duration"]
MS_COLUMNS_FALLBACK = [c for c in MS_COLUMNS if c != "album_artist"]
UNKNOWN = {None, "", "<unknown>"}
EXAMPLES = 10


# --- adb ------------------------------------------------------------------

def adb(*args, check=True):
    res = subprocess.run(["adb", *args], capture_output=True)
    if check and res.returncode != 0:
        sys.exit(f"adb {' '.join(args)} failed:\n"
                 + res.stderr.decode(errors="replace"))
    return res


def shell(command):
    return adb("exec-out", command).stdout.decode("utf-8", errors="replace")


def normalize_dir(d):
    d = d.rstrip("/")
    for alias in ("/sdcard", "/storage/self/primary"):
        if d == alias or d.startswith(alias + "/"):
            d = "/storage/emulated/0" + d[len(alias):]
    return d


def dir_exists(d):
    return shell(f"test -d {shlex.quote(d)} && echo yes").strip() == "yes"


def default_dirs():
    dirs = ["/storage/emulated/0/Music"]
    for name in shell("ls /storage").split():
        if re.fullmatch(r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}", name):
            dirs.append(f"/storage/{name}/Music")
    return [d for d in dirs if dir_exists(d)]


def list_files(d):
    out = shell(f"find {shlex.quote(d)} -type f 2>/dev/null")
    return [line for line in out.splitlines() if line]


def query_mediastore():
    out = ""
    for cols in (MS_COLUMNS, MS_COLUMNS_FALLBACK):
        out = shell(f"content query --uri {MS_URI} --projection {':'.join(cols)}")
        if out.startswith("Row:") or "No result found" in out:
            return cols, *parse_rows(out, cols)
    sys.exit("MediaStore query failed:\n" + out[:2000])


def parse_rows(out, cols):
    """Parse `content query` output. Values are not escaped, so match each
    row against the projection's column order rather than splitting on ', '."""
    pattern = re.compile(
        r"Row: \d+ " + ", ".join(re.escape(c) + "=(.*?)" for c in cols) + r"\Z",
        re.S)
    chunks = []
    for line in out.splitlines():
        if line.startswith("Row: "):
            chunks.append(line)
        elif chunks:  # a value with a newline in it
            chunks[-1] += "\n" + line
    rows, unparsed = [], 0
    for chunk in chunks:
        m = pattern.match(chunk)
        if not m:
            unparsed += 1
            continue
        rows.append({c: (None if v == "NULL" else v)
                     for c, v in zip(cols, m.groups())})
    return rows, unparsed


# --- helpers --------------------------------------------------------------

def ext_of(path):
    name = PurePosixPath(path).name
    if name.startswith(".") and name.count(".") == 1:
        return "(none)"
    suffix = PurePosixPath(path).suffix.lower().lstrip(".")
    return suffix or "(none)"


def parent(path):
    return str(PurePosixPath(path).parent)


def to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def norm_text(s):
    s = unicodedata.normalize("NFKC", s or "").casefold().strip()
    s = re.sub(r"\s+", " ", s)
    return s[4:] if s.startswith("the ") else s


def root_of(path, roots):
    for r in roots:
        if path == r or path.startswith(r + "/"):
            return r
    return None


def md(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def table(headers, rows):
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(md(c) for c in r) + " |" for r in rows]
    return out


def pct(n, total):
    return f"{n} ({n * 100 / total:.0f}%)" if total else str(n)


def location_of(path):
    """Top-level folder of a path: /storage/emulated/0/<X> or /storage/<sd>/<X>."""
    parts = PurePosixPath(path).parts
    depth = 5 if len(parts) > 2 and parts[2] == "emulated" else 4
    return str(PurePosixPath(*parts[:depth])) if len(parts) > depth else parent(path)


# --- tags via ffprobe -----------------------------------------------------

TAG_FIELDS = {
    "title": ("title",),
    "artist": ("artist",),
    "album": ("album",),
    "album artist": ("album_artist", "albumartist", "album artist"),
    "track": ("track", "tracknumber"),
    "disc": ("disc", "discnumber"),
    "date": ("date", "year", "originaldate"),
    "genre": ("genre",),
}


def probe(path):
    res = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        capture_output=True)
    if res.returncode != 0:
        return None
    data = json.loads(res.stdout or b"{}")
    tags = {k.lower(): v for k, v in
            ((data.get("format") or {}).get("tags") or {}).items()}
    audio = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]
    for s in audio:  # Ogg/Opus keep their tags on the stream
        for k, v in (s.get("tags") or {}).items():
            tags.setdefault(k.lower(), v)
    mb_keys = sorted(k for k in tags if "musicbrainz" in k)
    squashed = {re.sub(r"[\s_]", "", k) for k in mb_keys}
    return {
        "codec": audio[0].get("codec_name") if audio else None,
        "fields": {f for f, keys in TAG_FIELDS.items()
                   if any(tags.get(k) for k in keys)},
        "mb_keys": mb_keys,
        # Vorbis/FLAC MUSICBRAINZ_TRACKID and MP4 "MusicBrainz Track Id" hold
        # the recording ID. MP3 keeps it in a UFID frame ffprobe may not show.
        "mb_recording": "musicbrainztrackid" in squashed,
    }


def pick_sample(audio_files, n, rng):
    by_ext = collections.defaultdict(list)
    for p in audio_files:
        by_ext[ext_of(p)].append(p)
    picked = []
    for ext, paths in sorted(by_ext.items()):
        take = 3 if ext in MULTI_CODEC_EXTS else 1
        picked += rng.sample(paths, min(take, len(paths)))
    chosen = set(picked)
    seen_dirs = {parent(p) for p in picked}
    rest = [p for p in audio_files if p not in chosen]
    rng.shuffle(rest)
    for p in rest:  # fill up, one file per folder
        if len(picked) >= n:
            break
        if parent(p) not in seen_dirs:
            picked.append(p)
            seen_dirs.add(parent(p))
    return picked


# --- report ---------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dirs", nargs="*",
                    help="music folders on the phone (default: Music/ on "
                         "internal storage and each SD card)")
    ap.add_argument("--sample", type=int, default=10,
                    help="files to pull and probe with ffprobe; every format "
                         "gets at least one (default 10, 0 to skip)")
    ap.add_argument("--local-copy", type=Path,
                    help="a copy of the library on this PC: probe every audio "
                         "file in it for tags and codecs")
    ap.add_argument("-o", "--output", type=Path,
                    default=Path("mediastore-report.md"))
    args = ap.parse_args()

    if not shutil.which("adb"):
        sys.exit("adb not found (Arch: pacman -S android-tools)")
    state = adb("get-state", check=False)
    if state.stdout.decode().strip() != "device":
        sys.exit("No phone ready over adb: "
                 + (state.stderr.decode().strip() or state.stdout.decode().strip())
                 + "\nConnect it, enable USB debugging and accept the prompt. "
                   "With several devices, set ANDROID_SERIAL.")
    has_ffprobe = shutil.which("ffprobe") is not None

    roots = [normalize_dir(d) for d in args.dirs] or default_dirs()
    for r in roots:
        if not dir_exists(r):
            sys.exit(f"Not a folder on the phone: {r}")
    if not roots:
        sys.exit("No Music/ folder found; pass your music folder(s) as arguments.")
    multi_root = len(roots) > 1

    def rel(path):
        r = root_of(path, roots)
        if r is None:
            return path
        sub = path[len(r) + 1:]
        return f"[{r}] {sub}" if multi_root else sub

    print("Listing files on the phone…", file=sys.stderr)
    disk = {r: list_files(r) for r in roots}
    all_files = [p for files in disk.values() for p in files]
    disk_set = set(all_files)
    audio_files = [p for p in all_files if ext_of(p) in AUDIO_EXTS]
    nomedia_dirs = {parent(p) for p in all_files
                    if PurePosixPath(p).name == ".nomedia"}

    print("Querying MediaStore…", file=sys.stderr)
    cols, ms_rows, unparsed = query_mediastore()
    has_aa = "album_artist" in cols
    ms_in = [r for r in ms_rows if r["_data"] and root_of(r["_data"], roots)]
    ms_out = [r for r in ms_rows if not (r["_data"] and root_of(r["_data"], roots))]
    ms_paths = {r["_data"] for r in ms_in}

    L = ["# MediaStore vs library", ""]
    L += ["Folders scanned: " + ", ".join(f"`{r}`" for r in roots), ""]

    # 1. Counts per format
    disk_ext = collections.Counter(ext_of(p) for p in audio_files)
    indexed = [r for r in ms_in if r["_data"] in disk_set]
    ms_ext = collections.Counter(ext_of(r["_data"]) for r in indexed)
    L += ["## Audio files per format", ""]
    rows = []
    for ext in sorted(set(disk_ext) | set(ms_ext), key=lambda e: -disk_ext[e]):
        if ext in V1_EXTS:
            v1 = "yes" if ext not in MULTI_CODEC_EXTS else "yes (check codec below)"
        else:
            v1 = "**no**" if ext in AUDIO_EXTS else "?"
        rows.append((ext, disk_ext[ext], ms_ext[ext], v1))
    rows.append(("**total**", len(audio_files), len(indexed), ""))
    L += table(["format", "on disk", "indexed by MediaStore", "v1 decoders"], rows)
    other = collections.Counter(ext_of(p) for p in all_files
                                if ext_of(p) not in AUDIO_EXTS
                                and PurePosixPath(p).name != ".nomedia")
    if other:
        L += ["", "Other files in the folders: "
              + ", ".join(f"{e} {n}" for e, n in other.most_common())]
    L += [""]

    # 2. MediaStore overall
    L += ["## MediaStore", ""]
    L += [f"- Audio rows on the whole device: {len(ms_rows)}"
          + (f" ({unparsed} rows could not be parsed)" if unparsed else "")]
    L += [f"- Inside the scanned folders: {len(ms_in)}"]
    not_music = [r for r in ms_in if r["is_music"] in ("0", None)]
    L += [f"- Of those, flagged `is_music=0` (hidden if the app filters on it): "
          f"{len(not_music)}"]
    for r in not_music[:EXAMPLES]:
        L += [f"  - `{md(rel(r['_data']))}`"]
    stale = [r for r in ms_in if r["_data"] not in disk_set]
    L += [f"- Rows pointing at files that no longer exist: {len(stale)}"]
    if ms_out:
        where = collections.Counter(location_of(r["_data"] or "?") for r in ms_out)
        L += [f"- Audio outside the scanned folders: {len(ms_out)} rows"]
        for loc, n in where.most_common(15):
            music = sum(1 for r in ms_out if location_of(r["_data"] or "?") == loc
                        and r["is_music"] == "1")
            L += [f"  - `{md(loc)}`: {n} ({music} with is_music=1)"]
    L += [""]

    # 3. Missing from MediaStore
    missing = [p for p in audio_files if p not in ms_paths]
    L += ["## On disk but not in MediaStore", "", f"{len(missing)} audio files."]
    if missing:
        def cause(p):
            if any(p.startswith(d + "/") for d in nomedia_dirs):
                return "under a .nomedia folder"
            r = root_of(p, roots)
            if any(part.startswith(".")
                   for part in PurePosixPath(p[len(r) + 1:]).parts):
                return "hidden (dot) folder or file"
            return "no obvious reason"
        by_cause = collections.Counter((cause(p), ext_of(p)) for p in missing)
        L += [""] + table(["likely cause", "format", "files"],
                          [(c, e, n) for (c, e), n in by_cause.most_common()])
        L += ["", "Examples:"]
        for p in sorted(missing)[:EXAMPLES * 2]:
            L += [f"- `{md(rel(p))}`"]
    if nomedia_dirs:
        L += ["", ".nomedia files in: " + ", ".join(
            f"`{md(rel(d) or d)}`" for d in sorted(nomedia_dirs))]
    L += [""]

    # 4. Tag quality, as MediaStore read it
    songs = ms_in
    n = len(songs)
    L += ["## Tags as MediaStore reads them", "", f"{n} songs in the scanned folders.", ""]
    if n:
        no_title = [r for r in songs if r["title"] in UNKNOWN
                    or r["title"] == PurePosixPath(r["_data"]).stem]
        no_artist = [r for r in songs if r["artist"] in UNKNOWN]
        no_album = [r for r in songs if r["album"] in UNKNOWN]
        no_track = [r for r in songs if not to_int(r["track"])]
        L += [f"- Title missing or equal to the file name (MediaStore's fallback): "
              f"{pct(len(no_title), n)}",
              f"- Artist missing: {pct(len(no_artist), n)}",
              f"- Album missing: {pct(len(no_album), n)}",
              f"- Track number missing: {pct(len(no_track), n)}"]
        if has_aa:
            no_aa = [r for r in songs if r["album_artist"] in UNKNOWN]
            L += [f"- Album artist missing: {pct(len(no_aa), n)}"]

        by_folder = collections.defaultdict(list)
        for r in songs:
            by_folder[parent(r["_data"])].append(r)
        mixed = [(f, sorted({r["album"] or "∅" for r in rs}))
                 for f, rs in by_folder.items()
                 if len({r["album"] for r in rs}) > 1]
        L += [f"- Folders whose songs carry more than one album name: "
              f"{len(mixed)} of {len(by_folder)}"]
        for f, albums in mixed[:EXAMPLES]:
            L += [f"  - `{md(rel(f))}`: " + " / ".join(md(a) for a in albums[:4])]

        if has_aa:
            by_album = collections.defaultdict(list)
            for r in songs:
                by_album[(parent(r["_data"]), r["album"])].append(r)
            comps = [(k, rs) for k, rs in by_album.items()
                     if len({r["artist"] for r in rs}) > 1
                     and all(r["album_artist"] in UNKNOWN for r in rs)]
            L += [f"- Albums with several artists and no album artist "
                  f"(would split by artist): {len(comps)}"]
            for (f, album), rs in comps[:EXAMPLES]:
                L += [f"  - {md(album)} (`{md(rel(f))}`): "
                      f"{len({r['artist'] for r in rs})} artists"]

        variants = collections.defaultdict(collections.Counter)
        for r in songs:
            if r["artist"] not in UNKNOWN:
                variants[norm_text(r["artist"])][r["artist"]] += 1
        multi = [c for c in variants.values() if len(c) > 1]
        L += [f"- Artists spelled more than one way: {len(multi)}"]
        for c in multi[:EXAMPLES]:
            L += ["  - " + " / ".join(f"{md(a)} ({k})" for a, k in c.most_common())]
    L += [""]

    # 5. Likely duplicates
    L += ["## Likely duplicates", ""]
    groups = collections.defaultdict(list)
    for r in songs:
        if r["title"] in UNKNOWN or r["artist"] in UNKNOWN:
            continue
        groups[(norm_text(r["title"]), norm_text(r["artist"]))].append(r)
    dups = []
    for rs in groups.values():
        if len(rs) < 2:
            continue
        rs.sort(key=lambda r: to_int(r["duration"]) or 0)
        cluster = [rs[0]]
        for r in rs[1:]:
            if abs((to_int(r["duration"]) or 0)
                   - (to_int(cluster[-1]["duration"]) or 0)) <= 2000:
                cluster.append(r)
            else:
                if len(cluster) > 1:
                    dups.append(cluster)
                cluster = [r]
        if len(cluster) > 1:
            dups.append(cluster)
    cross_format = [d for d in dups if len({ext_of(r["_data"]) for r in d}) > 1]
    cross_folder = [d for d in dups if len({parent(r["_data"]) for r in d}) > 1]
    L += [f"Groups with the same title and artist and durations within 2 s: "
          f"{len(dups)} ({len(cross_format)} span formats, "
          f"{len(cross_folder)} span folders)."]
    for d in dups[:EXAMPLES]:
        L += [f"- {md(d[0]['artist'])} – {md(d[0]['title'])}: "
              + ", ".join(f"`{md(rel(r['_data']))}`" for r in d)]
    L += [""]

    # 6. Tag sample via ffprobe
    L += ["## Tag sample (ffprobe)", ""]
    if args.sample <= 0:
        L += ["Skipped (--sample 0)."]
    elif not has_ffprobe:
        L += ["Skipped: ffprobe not found (Arch: pacman -S ffmpeg)."]
    elif not audio_files:
        L += ["No audio files to sample."]
    else:
        sample = pick_sample(audio_files, args.sample, random.Random())
        print(f"Pulling {len(sample)} sample files…", file=sys.stderr)
        rows = []
        with tempfile.TemporaryDirectory() as tmp:
            for i, p in enumerate(sample):
                local = Path(tmp) / f"{i}.{ext_of(p)}"
                if adb("pull", p, str(local), check=False).returncode != 0:
                    rows.append((rel(p), ext_of(p), "pull failed", "", ""))
                    continue
                info = probe(local)
                local.unlink(missing_ok=True)
                if info is None:
                    rows.append((rel(p), ext_of(p), "probe failed", "", ""))
                    continue
                codec = info["codec"] or "?"
                if codec not in V1_CODECS:
                    codec = f"**{codec}**"
                rows.append((rel(p), ext_of(p), codec,
                             ", ".join(f for f in TAG_FIELDS if f in info["fields"]),
                             ", ".join(info["mb_keys"]) or "none"))
        with_mb = sum(1 for r in rows if r[4] not in ("none", ""))
        L += [f"{with_mb} of {len(rows)} sampled files carry MusicBrainz tags. "
              "Codecs outside the v1 decoders are in bold. For MP3 the "
              "MusicBrainz recording ID sits in a UFID frame that ffprobe may "
              "not list, so judge MP3s by the other MusicBrainz tags.", ""]
        L += table(["file", "format", "codec", "tags present", "MusicBrainz tags"], rows)
    L += [""]

    # 7. Optional: the whole PC copy
    if args.local_copy:
        L += ["## PC copy (every file probed)", ""]
        if not has_ffprobe:
            L += ["Skipped: ffprobe not found."]
        else:
            files = [p for p in args.local_copy.rglob("*")
                     if p.is_file() and p.suffix.lower().lstrip(".") in AUDIO_EXTS]
            print(f"Probing {len(files)} files in {args.local_copy}…", file=sys.stderr)
            with concurrent.futures.ThreadPoolExecutor(os.cpu_count() or 4) as pool:
                infos = [i for i in pool.map(probe, files) if i]
            total = len(infos)
            codecs = collections.Counter(i["codec"] or "?" for i in infos)
            L += [f"- Files probed: {total} of {len(files)}",
                  "- Codecs: " + ", ".join(
                      f"{c if c in V1_CODECS else '**' + c + '**'} {k}"
                      for c, k in codecs.most_common()),
                  f"- Any MusicBrainz tag: {pct(sum(1 for i in infos if i['mb_keys']), total)}",
                  f"- MusicBrainz recording ID visible (non-MP3): "
                  f"{pct(sum(1 for i in infos if i['mb_recording']), total)}"]
            for field in TAG_FIELDS:
                L += [f"- Missing {field}: "
                      f"{pct(sum(1 for i in infos if field not in i['fields']), total)}"]
        L += [""]

    L += ["---", "_Contains file, folder and song names. Trim anything you "
          "don't want public before posting._"]
    report = "\n".join(L) + "\n"
    args.output.write_text(report, encoding="utf-8")
    print(report)
    print(f"Report written to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
