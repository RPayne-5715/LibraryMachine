# Library Machine

A personal music library manager built with Python and Kivy for Android, with a Windows development interface. Library Machine imports YouTube playlists into a master CSV, downloads audio as Opus files, and uses CSV metadata to maintain filenames, audio tags, and local playlists.

## Features

- Import a YouTube or YouTube Music playlist by pasting its URL.
- Extract video URLs, titles, and artist information for manual review.
- Download audio as `.opus` files with embedded thumbnails.
- Edit library metadata through `music_database.csv`.
- Synchronize filenames and title, artist, album, genre, and source URL tags.
- Generate four cumulative `.m3u8` playlists based on assigned layers.
- Display progress, validation errors, and download results in the app console.

## Usage

1. On Android, grant the requested **All files access** permission. The library is stored in `/storage/emulated/0/Music/PlaylistLibrary`.
2. Copy a playlist URL, press **Playlist**, then **Paste**.
3. Wait for analysis. If unavailable videos are reported, fix the source playlist and press **Continue** to retry.
4. When prompted, open `music_database.csv` in a CSV editor. Review titles and artists, fill in genres, and optionally assign layers. Save the file before returning to the app.
5. Press **Continue** to validate the CSV, download missing tracks, and generate local playlists.

After editing existing entries, press **Sync CSV** to apply metadata and filename changes. If tracks are missing, choose **Y** to download them before synchronizing or **N** to synchronize existing files only.

**Sync CSV can delete duplicate audio files:** files sharing the same source URL in their comment tag are treated as duplicates, and the file with the newest modification time is retained.

## CSV format

The first seven columns must appear in this order:

```csv
date_added,video_url,title,artist,layer,genre,downloaded
2026-10-23,https://youtu.be/VIDEO_ID,Example Song,Example Artist,1,Pop,NO
```

| Column | Purpose |
| --- | --- |
| `date_added` | Import date in `YYYY-MM-DD` format. Blank values become `Unknown` when read. |
| `video_url` | Required source URL; also stored in the audio comment tag for indexing. |
| `title` | Track title and the first part of its filename. |
| `artist` | Required artist name and the second part of its filename. |
| `layer` | Blank or a number from `1` through `4`. |
| `genre` | Required genre text, supplied manually. |
| `downloaded` | `YES` or `NO`; updated during downloading and library indexing. |

The CSV uses UTF-8 with a BOM. Additional columns after the required columns are preserved during normal rewrites. New imports leave genre and layer blank; genre must be filled before validation succeeds.

Audio filenames use `Title - Artist.opus`, with unsupported filename characters replaced by underscores. Renaming or retagging an existing track should be done through the CSV followed by **Sync CSV**.

## Layers and generated playlists

| Layer | Album tag | Generated playlist | Included layers |
| --- | --- | --- | --- |
| `1` | Dollop | `Dollop.m3u8` | 1 |
| `2` | Peer | `Peer.m3u8` | 1–2 |
| `3` | PeerJ | `PeerJ.m3u8` | 1–3 |
| `4` | For Dakota ig | `For Dakota_ig.m3u8` | 1–4 |

Tracks with a blank layer are excluded from generated playlists and receive the album tag `Blank` when tagged. Playlist entries use filenames relative to the library folder; only rows marked `YES` are included.

## Project files

| Path | Role |
| --- | --- |
| `main.py` | Kivy application, Android integration, and background task coordination. |
| `backend.py` | Playlist analysis, CSV validation, downloads, tagging, and synchronization. |
| `librarymachine.kv` | Screens, button styles, console, and progress display. |
| `buildozer.spec` | Android packaging configuration. |
| `assets/` | Images and fonts used by the interface. |
| `vendor/` | Local Python dependencies or patched packages; searched before installed packages by the backend. |
| `ffmpeg/windows/` | Windows FFmpeg tools. |
| `ffmpeg/android/` | Android FFmpeg tools. |

## Windows development

From the directory containing `main.py`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install kivy yt-dlp mutagen pytubefix certifi
python main.py
```

Keep any project-specific patched dependencies in `vendor/`. Supply FFmpeg and FFprobe in `ffmpeg/windows/`, along with the images and fonts referenced by the application:

- `assets/presplash.png`
- `assets/progress_gradient.png`
- `assets/CourierPrime-Regular.ttf`
- `assets/Jua-Regular.ttf`

The desktop library path is calculated as `Path(__file__).resolve().parent.parent.parent / "PlaylistLibrary"` in `main.py`. Check that location before running from a different checkout layout. Desktop file-opening actions use Windows `os.startfile()`.

## Android build

Use the project's configured Buildozer/python-for-android environment. From the project directory inside that environment:

```bash
buildozer -v android debug
```

Build output is written to `bin/` unless configured otherwise. Android packaging must include the project's vendored dependencies, assets, and compatible executable FFmpeg tools. The supplied build specification targets `arm64-v8a` and requests internet and all-files access. Its dependency list must match the current code, including the `pytubefix` import or its vendored copy.

To inspect device logs with ADB available:

```bash
adb logcat PythonActivity:V python:V SDL:V AndroidRuntime:E '*:S'
```

## Current limitations

- Playlist import duplicate detection is incomplete in the reviewed source: `filter_duplicates()` reads the first CSV column as a URL, although that column is now `date_added`. Reimporting a playlist can therefore append duplicate rows.
- The Android **Open CSV** handler launches a CSV viewer intent without attaching the database URI. Open the database directly in your editor until file handoff is implemented.
- YouTube synchronization and CSV pull handlers are placeholders; the current interface exposes playlist import and CSV synchronization.
- Downloads can fail independently. Check the console result counts even when the workflow reports completion.

This README describes the supplied source snapshot. The Android build and runtime behavior have not been verified as part of this documentation update.
