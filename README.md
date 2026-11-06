# Library Machine

A personal music library manager built with Python and Kivy for Android, with a Windows interface for development. It imports YouTube playlists into a master CSV, downloads songs as Opus files, and uses the spreadsheet to keep filenames, tags, and local playlists in sync.

Built for a **Pixel8**. See [`buildozer.spec`](buildozer.spec) for compatibility details.

## Features

- Import YouTube and YouTube Music playlists from a share link.
- Pull video URLs, titles, and artist names into a CSV for you to review.
- Download songs as `.opus` files with embedded thumbnails.
- Manage metadata through `music_database.csv`.
- Sync filenames and title, artist, album, genre, and source URL tags.
- Generate four cumulative `.m3u8` playlists using layers.
- Show progress, errors, and download results in the app console.

## Usage

This is mostly meant for maintaining my existing music library. You can build a library from scratch with it, but be prepared to spend 7-10 business days in the spreadsheet.

Expected paths are Music/PlaylistLibrary for PC, and "/storage/emulated/0/Music/PlaylistLibrary" for android. These can be changed in main.py

If there's no `music_database.csv`, the app creates one when you import a playlist.

1. Put the songs you want to add in a public or unlisted YouTube or YouTube Music playlist and copy its share link.
2. Press **Playlist**, then **Paste**.
3. Wait for the app to analyze the playlist and add the entries to `music_database.csv`.
4. Press **Open CSV**. Fix up titles and artists, fill in genres, and assign layers if you want them in the generated playlists.
5. Save the CSV, return to the app, and press **Continue** to download the songs and build the playlists.

The app uses [CSVLabs](https://play.google.com/store/apps/details?id=com.livinlabs.csvforge) for editing. **Open CSV** opens the editor, open `music_database.csv` directly in the editor.

### Updating your library

Edit the CSV, save it, then press **Sync CSV** to update filenames, tags, and playlists. If you change audio tags or filenames outside the app, the next sync may overwrite those changes.

If songs are missing, choose **Y** to download them before syncing or **N** to just sync the files you already have.

Files with the same source URL in their comment tag count as duplicates. When indexing the library, the app keeps whichever file was modified most recently and deletes the others.

Any readable Opus files in the folder that are not in the csv WILL be deleted.

### Failed downloads

Some downloads will fail. Try running **Sync CSV** again; a retry will often work.

If a song keeps failing, the video might be unavailable or restricted. Try replacing its source URL in the CSV with another upload of the same song, such as a lyric video or fan upload.

If the songs are repeatedly failing with 403 errors, feel free to spit upon the name of youtube and run `adb logcat python:V AndroidRuntime:E '*:S'` to figure out what broke

## CSV format

The first seven columns need to stay in this order:

```csv
date_added,video_url,title,artist,layer,genre,downloaded
2026-10-23,https://youtu.be/VIDEO_ID,Example Song,Example Artist,1,Pop,NO
```

| Column | Entry | What it's for |
| --- | --- | --- |
| `date_added` | Automatic | For viewer's knowledge only, changing this value has no effect. Date imported, formatted as `YYYY-MM-DD`. Blank values are read as `Unknown`. |
| `video_url` | Required | Source URL. Also stored in the audio comment tag so the app can identify the file. Uses youtu.be format |
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

Each layer has a playlist, and they stack. A playlist includes its own layer and every lower-numbered layer. The song's album tag comes from its assigned layer.

| Layer | Album tag | Playlist file | Included layers |
| --- | --- | --- | --- |
| `1` | Dollop | `Dollop.m3u8` | 1 |
| `2` | Peer | `Peer.m3u8` | 1–2 |
| `3` | PeerJ | `PeerJ.m3u8` | 1–3 |
| `4` | For Dakota ig | `For Dakota_ig.m3u8` | 1–4 |

These names can be changed in backend.py.

Songs with a blank layer stay out of the generated playlists and get the album tag `Blank` when tagged.

**The `.m3u8` paths are relative.** Each entry is just the audio filename, resolved from the folder containing the playlist. Keep the playlist files alongside the `.opus` files. You can move the whole folder together without changing the paths, but moving a playlist somewhere else will break its references.

Within each playlist, songs appear in CSV row order. Layers decide which songs are included; they don't change the sorting.

## Project files

| Path | What's in it |
| --- | --- |
| `main.py` | Kivy app, Android integration, and background tasks. |
| `backend.py` | Playlist analysis, CSV handling, downloads, tagging, and syncing. |
| `librarymachine.kv` | Screens, button styles, console, and progress display. |
| `buildozer.spec` | Android build configuration and explicit dependency pins. |
| `build-constraints.txt` | pip constraints used during Android builds. |
| `build-host-requirements.txt` | Python packages for the Docker build environment. |
| `build-tools/` | Saved Buildozer source, environment notes, and binary checksums. |
| `recipes/nodejs/` | Android Node executable packaging and Python runtime helper. |
| `assets/` | Images and fonts. |
| `vendor/` | Local dependencies and patched packages, loaded before installed packages by the backend. |
| `ffmpeg/windows/` | Windows FFmpeg tools. |
| `ffmpeg/android/` | Android FFmpeg tools. |

## Windows development

From the folder containing `main.py`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install "kivy==2.3.1" "yt-dlp[default]==2026.10.26" "yt-dlp-ejs==0.8.0" "mutagen==1.48.1" "certifi==2026.10.23" pytubefix nodejs-wheel-binaries
python main.py
```

Install Node.js and make sure `node --version` works in the terminal used to start the app. yt-dlp uses Node and `yt-dlp-ejs` to solve YouTube's JavaScript challenges. `nodejs-wheel-binaries` is also needed by the vendored pytubefix imports on Windows; it is not the Android Node runtime.

Keep the project's patched dependencies in `vendor/`. Put FFmpeg and FFprobe in `ffmpeg/windows/`, and keep these files in `assets/`:

- `presplash.png`
- `progress_gradient.png`
- `CourierPrime-Regular.ttf`
- `Jua-Regular.ttf`

The Windows library path is set in `main.py`:

```python
Path.home() / "Music" / "PlaylistLibrary"
```

Check where that points if your folder layout is different. Opening files from the desktop app uses Windows `os.startfile()`.

## Android build

The project includes `buildozer.spec` and a customized copy of `pytubefix`. Use the project's patched dependencies when building; installing the standard packages might not give you the same results and may cause significant hair loss.

This was not built for wide compatibility, so expect some fiddling if you're building it yourself. I did my best to pin everything I could

### Working build versions

These versions were checked against the working Android build and its Docker environment as of 11/5. Host Python runs Buildozer; Android Python is bundled into the app.

| Component | Verified version |
| --- | --- |
| Host Python | 3.14.4 |
| Buildozer | Local source reporting `1.6.1.dev0`, saved as `build-tools/buildozer-working-source.tar.gz` |
| python-for-android | `58d21141f17c889bf8585f5665921d72028f8831` |
| Java | OpenJDK `17.0.18+8-Ubuntu-1` |
| Android SDK Build Tools | 37.0.0 |
| Android target / minimum API | 33 / 24 |
| Android NDK / NDK API | r28c (`28.2.13676358`) / 24 |
| Architecture | arm64-v8a |
| Gradle / Android Gradle Plugin | 8.14.3 / 8.11.0 |
| Android Python | 3.14.2 |
| Kivy / pyjnius | 2.3.1 / 1.7.0 |
| yt-dlp / yt-dlp-ejs | 2026.10.26 / 0.8.0 |
| mutagen | 1.48.1 |
| certifi / charset-normalizer | 2026.10.23 / 2.1.1 |
| Host / Android setuptools | 83.0.0 / 84.2.1 |
| Android FFmpeg / FFprobe | 8.1.1 |

Keep the spec, constraints, host requirements, local recipes, and saved binaries with the project. The Buildozer version string alone does not identify the saved development source. Use the saved archive rather than substituting a published release. The host requirements entry for it is `./build-tools/buildozer-working-source.tar.gz`.

`android.skip_update = True` prevents automatic SDK upgrades. It is not a Build Tools version pin: a fresh SDK must have Build Tools 37.0.0 installed, and newer installed versions can change which version is selected. Java and host Python must also be supplied by the Docker environment.

### Android executables

The custom Node recipe downloads Android ARM64 binaries from a fixed source commit and verifies their SHA-256 checksums. Keep `nodejs` in the Android requirements so python-for-android uses that recipe. Do not substitute `nodejs-wheel-binaries`: it previously packaged a Linux x86-64 executable from the build host.

Node, FFmpeg, and FFprobe must run from Android's installed native-library directory. Executing copies under the app's writable data directory is blocked by Android's execution policy; adding executable permissions does not fix it.

The APK must contain:

```text
lib/arm64-v8a/libnode_exec.so
lib/arm64-v8a/libffmpeg.so
lib/arm64-v8a/libffprobe.so
```

`recipes/nodejs/runtime.py` supplies Node's installed path. `PathStorage.ffmpeg_location()` supplies the installed `libffmpeg.so` path, and yt-dlp finds `libffprobe.so` alongside it. The `.so` names are for Android packaging; these files are invoked as executables.

### Build and check

From the project root inside the configured Docker environment:

```bash
sha256sum -c build-tools/SHA256SUMS
buildozer -v android debug
```

Check the resulting APK, replacing `x.x` if the app version changes:

```bash
unzip -l bin/librarymachine-x.x-arm64-v8a-debug.apk | grep -E 'lib/arm64-v8a/lib(node_exec|ffmpeg|ffprobe)\.so'
```

All three executables should appear. Test a download inside the installed app as well: a successful `adb shell run-as` test does not prove the app itself can execute the same file.

## Known issues and unfinished bits

- **Mojibake:** Some text still comes through garbled.
- **Clearing layers:** Synchronization can leave the previous album tag when a CSV layer is cleared. The intended replacement is `Blank`; the sync comparison needs to handle empty layers too.
- **Planned:** Volume normalization tags, potentially ReplayGain, followed by layer renaming and automatic creation of additional layers from CSV values such as `5` or `6`. These are not implemented yet.
