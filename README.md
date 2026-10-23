# Library Machine

A personal music library manager built with Python and Kivy for Android, with a Windows interface for development. It imports YouTube playlists into a master CSV, downloads songs as Opus files, and uses the spreadsheet to keep filenames, tags, and local playlists in sync.

Built for a **Pixel8**. See [`buildozer.spec`](buildozer.spec) for build settings and compatibility details.

## Features

- Import YouTube and YouTube Music playlists from a share link.
- Pull video URLs, titles, and artist names for you to review.
- Download songs as `.opus` files with embedded thumbnails.
- Manage metadata through `music_database.csv`.
- Sync filenames and title, artist, album, genre, and source URL tags.
- Generate four cumulative `.m3u8` playlists using layers.
- Show progress, errors, and download results in the app console.

## Usage

This is mostly meant for maintaining my existing music library. You can build a library from scratch with it, but be prepared to spend 7-10 business days in the spreadsheet.

On first launch, select your music library folder. If there's no `music_database.csv`, the app creates one when you import a playlist.

1. Put the songs you want to add in a YouTube or YouTube Music playlist and copy its share link.
2. Press **Playlist**, then **Paste**.
3. Wait for the app to analyze the playlist and add the entries to `music_database.csv`.
4. Press **Open CSV**. Fix up titles and artists, fill in genres, and assign layers if you want them in the generated playlists.
5. Save the CSV, return to the app, and press **Continue** to download the songs and build the playlists.

The app uses [CSVLabs](https://play.google.com/store/apps/details?id=com.livinlabs.csvforge) for editing. If **Open CSV** doesn't open the database, open `music_database.csv` directly in the editor.

### Updating your library

Edit the CSV, save it, then press **Sync CSV** to update filenames, tags, and playlists. If you change audio tags or filenames outside the app, the next sync may overwrite those changes.

If songs are missing, choose **Y** to download them before syncing or **N** to just sync the files you already have.

Files with the same source URL in their comment tag count as duplicates. When indexing the library, the app keeps whichever file was modified most recently and deletes the others.

### Failed downloads

Some downloads will fail. Try running **Sync CSV** again; a retry will often work.

If a song keeps failing, the video might be unavailable or restricted. Try replacing its source URL in the CSV with another upload of the same song, such as a lyric video or fan upload.

## CSV format

The first seven columns need to stay in this order:

```csv
date_added,video_url,title,artist,layer,genre,downloaded
2026-10-23,https://youtu.be/VIDEO_ID,Example Song,Example Artist,1,Pop,NO
```

| Column | Entry | What it's for |
| --- | --- | --- |
| `date_added` | Automatic | Date imported, formatted as `YYYY-MM-DD`. Blank values are read as `Unknown`. |
| `video_url` | Required | Source URL. Also stored in the audio comment tag so the app can identify the file. |
| `title` | Track title | Used for the title tag and filename. |
| `artist` | Required | Used for the artist tag and filename. |
| `layer` | Optional | Blank or `1`–`4`. Controls playlist membership and the album tag. |
| `genre` | Required | Filled in manually. |
| `downloaded` | App-managed | `YES` or `NO`, updated based on downloads and the files found when indexing. |

New imports leave genre and layer blank. You need to fill in genre before continuing, but layer can stay blank.

The CSV uses UTF-8 with a BOM. Some mojibake issues remain. Extra columns after the required ones are preserved during normal rewrites.

Files are named `Title - Artist.opus`. Characters that aren't allowed in filenames get replaced with underscores.

Generated playlists follow the order of the rows in the CSV. If you sort the table by artist, title, date, or anything else and save it, the next playlist rebuild will use that order. Sort whole rows together in a table format so each song's fields stay matched.

Note that Album art is pulled from the Youtube thumbnail.

## Layers and playlists

Each layer has a playlist. They stack. A playlist includes its own layer and every lower-numbered layer. The song's album tag comes from its assigned layer.

| Layer | Album tag | Playlist file | Included layers |
| --- | --- | --- | --- |
| `1` | Dollop | `Dollop.m3u8` | 1 |
| `2` | Peer | `Peer.m3u8` | 1–2 |
| `3` | PeerJ | `PeerJ.m3u8` | 1–3 |
| `4` | For Dakota ig | `For Dakota_ig.m3u8` | 1–4 |

These are my playlist names. They're currently hardcoded, so changing them means editing the code. My bad.

Songs with a blank layer stay out of the generated playlists and get the album tag `Blank` when tagged.

**The `.m3u8` paths are relative.** Each entry is just the audio filename, resolved from the folder containing the playlist. Keep the playlist files alongside the `.opus` files. You can move the whole folder together without changing the paths, but moving a playlist somewhere else will break its references.

Within each playlist, songs appear in CSV row order. Layers decide which songs are included; they don't change the sorting.

## Project files

| Path | What's in it |
| --- | --- |
| `main.py` | Kivy app, Android integration, and background tasks. |
| `backend.py` | Playlist analysis, CSV handling, downloads, tagging, and syncing. |
| `librarymachine.kv` | Screens, button styles, console, and progress display. |
| `buildozer.spec` | Android build configuration. |
| `assets/` | Images and fonts. |
| `vendor/` | Local dependencies and patched packages, loaded before installed packages by the backend. |
| `ffmpeg/windows/` | Windows FFmpeg tools. |
| `ffmpeg/android/` | Android FFmpeg tools. |

## Windows development

From the folder containing `main.py`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install kivy yt-dlp mutagen pytubefix certifi
python main.py
```

Keep the project's patched dependencies in `vendor/`. Put FFmpeg and FFprobe in `ffmpeg/windows/`, and keep these files in `assets/`:

- `presplash.png`
- `progress_gradient.png`
- `CourierPrime-Regular.ttf`
- `Jua-Regular.ttf`

The Windows library path is set in `main.py`:

```python
Path(__file__).resolve().parent.parent.parent / "PlaylistLibrary"
```

Check where that points if your folder layout is different. Opening files from the desktop app uses Windows `os.startfile()`.

## Android build

The project includes `buildozer.spec` and a customized copy of `pytubefix`. Use the project's patched dependencies when building; installing the standard packages might not give you the same results and may cause significant hair loss.

This was not built for wide compatibility, so expect some fiddling if you're building it yourself.

## Known issues and unfinished bits
aka Why There Are No Releases

- **Duplicate playlist imports:** In this source snapshot, `filter_duplicates()` still treats the first CSV column as a URL, even though it's now `date_added`. Importing the same playlist again can add duplicate rows.
- **Opening the CSV on Android:** The current handler opens a CSV viewer without passing it the database URI. You may need to open the file manually.
- **Unfinished handlers:** YouTube sync and CSV pull are placeholders and aren't shown in the current interface.
- **Mojibake:** Some text still comes through garbled.

These notes reflect the supplied source snapshot. The Android build and runtime weren't tested as of currently. In fact, as of currently the Android build is broke sooooooooooooooooooooooooooooooooo 
