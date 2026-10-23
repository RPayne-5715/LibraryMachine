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

This application expects a pre-existing music library, but will work without one. Trying to create a new music library with this tool will be a tedious and spreadsheet-heavy process but is doable.

1. **Add any songs you want to add to your library to a new playlist. Copy the share link of the playlist to your clipboard** Youtube or Youtube Music playlists will both work.
2. **Hit the Playlist button to start the process.**
3. **Wait for the app to finish appending the entries to `music_database.csv`**
4. **Hit the *Open CSV* button to open the CSV editor**. Edit titles, artists, genres, and playlist layers to your desires
  - Layers work as follows:
    - Each layer refers to a playlist
    - Each layer playlist contains all the songs of any layers beneath it.
    - Songs unique to each layer will be put in an album of the same name as the layer
    - There is no current way to change these names
5. **Save the CSV and return to the app. Proceed to downloading the songs**

***Notes:*** Some songs will return errors when trying to download. In most cases, rerunning the process via ***Sync CSV*** will fix the error and correctly download the song. If not, the issue is likely licensing. Replace the Video ID of the entry in the CSV with the Video ID of a fan upload or a lyric video of the song.

The app utilizes the following app for CSV editing.
https://play.google.com/store/apps/details?id=com.livinlabs.csvforge&hl=en-ZA

Built for Pixel8. See buildozer.spec for more compatibility information.

On first boot, the app lets you select the location of your music library.

If no CSV exists upon trying to download a playlist, a blank csv will be generated and filled

Files sharing the same source URL in their comment tag are treated as duplicates, and the file with the newest modification time is retained.

## CSV format

The first seven columns must appear in this order:

```csv
date_added,video_url,title,artist,layer,genre,downloaded
2026-10-23,https://youtu.be/VIDEO_ID,Example Song,Example Artist,1,Pop,NO
```

| Column | Required? | Purpose |
| --- | --- | --- |
| `date_added` | --- | Import date in `YYYY-MM-DD` format. Blank values become `Unknown` when read. |
| `video_url` | Yes | Required source URL; also stored in the audio comment tag for indexing. |
| `title` | Yes | Track title and the first part of its filename. |
| `artist` | Yes | Required artist name and the second part of its filename. |
| `layer` | No | Blank or a number from `1` through `4`. |
| `genre` | Yes | Genre, supplied manually. |
| `downloaded` | --- | `YES` or `NO`; updated during downloading and library indexing. Refers to the success of the download. |

The CSV uses UTF-8 with a BOM. Some Mojibake issues remain. Additional columns after the required columns are preserved during normal rewrites. New imports leave genre and layer blank; genre must be filled before validation succeeds.

Audio filenames use `Title - Artist.opus`, with unsupported filename characters replaced by underscores. Renaming or retagging an existing track should be done through the CSV followed by **Sync CSV**, else your changes will be over-written next sync.

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

Included is the Buildozer.spec and a customized pytubefix. Feel free to build yourself, idk.

## Current limitations

- Playlist import duplicate detection is incomplete in the reviewed source: `filter_duplicates()` reads the first CSV column as a URL, although that column is now `date_added`. Reimporting a playlist can therefore append duplicate rows.
- The Android **Open CSV** handler launches a CSV viewer intent without attaching the database URI. Open the database directly in your editor until file handoff is implemented.
- YouTube synchronization and CSV pull handlers are placeholders; the current interface exposes playlist import and CSV synchronization.

This README describes the supplied source snapshot. The Android build and runtime behavior have not been verified as part of this documentation update.
