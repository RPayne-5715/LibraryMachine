from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent / "vendor"))

from urllib.parse import urlparse, parse_qs
import csv
from datetime import datetime
import re
import textwrap
import yt_dlp
from mutagen.oggopus import OggOpus
from pytubefix import Playlist

import ssl
import certifi

ssl._create_default_https_context = lambda: ssl.create_default_context(
    cafile=certifi.where()
)

from kivy.utils import platform

LAYER_NAMES = {
    1: "Dollop",
    2: "Peer",
    3: "PeerJ",
    4: "For Dakota ig",
}

class SilentLogger:
    def debug(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        pass

class DownloadLogger:

    def __init__(self, log):
        self.last_error = None
        self.log = log

    def debug(self, msg):
        pass

    def warning(self, msg):
        if "No supported JavaScript runtime could be found" in msg:
            return

        self.log(f"WARNING: {msg}")

    def error(self, msg):
        self.last_error = msg

class PathStorage:

    def __init__(self, root):
        self.root = Path(root)

    def glob(self, pattern):
        return self.root.glob(pattern)

    def exists(self, path):
        return path.exists()

    def rename(self, src, dst):
        src.rename(dst)

    def unlink(self, path):
        path.unlink()

    def open_path(self, path, mode="r", **kwargs):
        return path.open(mode, **kwargs)

    def file(self, *parts):
        return self.root.joinpath(*parts)

    def ffmpeg_location(self):
        if platform == "android":
            return str(
                Path(__file__).resolve().parent
                / "ffmpeg"
                / "android"
            )

        return str(
            Path(__file__).resolve().parent
            / "ffmpeg"
            / "windows"
        )

class LibraryMachine:

    def __init__(self, library_path, log_callback=None, progress_callback=None):

        if isinstance(library_path, PathStorage):
            self.storage = library_path
        else:
            self.storage = PathStorage(library_path)
        self.library_path = self.storage.root

        self.master_csv = self.storage.file("music_database.csv")

        self.log = log_callback or (lambda msg="": None)
        self.progress = progress_callback or (lambda c, t: None)

        self.hrr = "================================"
        self.hr = "---------------------------"

    #

    def hyphenate_long_words(self, text, available):

        def repl(match):

            word = match.group(0)

            if len(word) <= available:
                return word

            pieces = []

            while len(word) > available:
                pieces.append(word[: available - 1] + "-")
                word = word[available - 1 :]

            pieces.append(word)

            return "\n".join(pieces)

        return re.sub(r"\S+", repl, text)

    def format_song(self, style, index, total, title, artist=""):

        if style == "download":
            prefix = f"({index}/{total}) "
            text = f"{title} - {artist}"

        elif style == "missing":
            prefix = f"({index}/{total}) "
            text = title

        elif style == "missing_video":
            prefix = f"{index}. "
            text = title

        elif style == "failed":
            prefix = "  - "
            text = title

        else:
            prefix = ""
            text = title

        available = 30 - len(prefix)

        text = self.hyphenate_long_words(text, available)

        return textwrap.fill(
            prefix + text,
            width=30,
            subsequent_indent=" " * len(prefix),
            break_long_words=False,
            break_on_hyphens=False,
        )

    def major(self, title=None):
        self.log("")
        self.log(self.hrr)
        self.log("")

        if title:
            self.log(title)
            self.log("")

    def report(self, title):
        self.log("")
        self.log(self.hr)
        self.log(title)
        self.log(self.hr)
        self.log("")

    def blank(self):
        self.log("")

    #

    def normalize_playlist_url(self, url):
        if "list=" not in url:
            return url

        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        playlist_ids = params.get("list")

        if not playlist_ids:
            return url

        return f"https://www.youtube.com/playlist?list={playlist_ids[0]}"

    def get_playlist_info(self, url):

        playlist = Playlist(url)

        entries = []

        for video_url in playlist.video_urls:

            video_id = video_url.split("v=")[1].split("&")[0]

            entries.append(
                {
                    "video_url": f"https://youtu.be/{video_id}",
                }
            )

        return {
            "title": playlist.title,
            "entries": entries,
        }

    def filter_duplicates(self, entries):

        if not self.master_csv.exists():
            self.major("Master CSV not found. Creating CSV...")
            with self.storage.open_path(self.master_csv, "w", encoding="utf-8-sig", newline="") as f:

                writer = csv.writer(f)

                writer.writerow(
                    [
                        "date_added",
                        "video_url",
                        "title",
                        "artist",
                        "layer",
                        "genre",
                        "downloaded",
                    ]
                )

            return entries, False

        existing_urls = set()

        with self.storage.open_path(self.master_csv, "r", encoding="utf-8-sig", newline="") as f:

            reader = csv.reader(f)

            next(reader, None)

            for row in reader:
                if row:
                    existing_urls.add(row[0].strip())

        new_entries = []

        for entry in entries:
            if entry["video_url"] not in existing_urls:
                new_entries.append(entry)

        duplicates_found = len(entries) - len(new_entries)

        if duplicates_found and new_entries:
            self.log(
                f"\n{duplicates_found} duplicate"
                f"{'' if duplicates_found == 1 else 's'} "
                "found. Skipping duplicates..."
            )

        return new_entries, True

    def analyze_entries(self, entries, layer):
        try:
            analysis_data = []
            missing_entries = []

            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "ignoreerrors": True,
                "logger": SilentLogger(),
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:

                total = len(entries)

                for current, entry in enumerate(entries, start=1):

                    self.progress(current, total)

                    try:
                        video_info = ydl.extract_info(entry["video_url"], download=False)

                        if not video_info:
                            raise Exception("Video unavailable")

                        artist = (
                            video_info.get("artist")
                            or video_info.get("uploader")
                            or video_info.get("channel")
                            or ""
                        )

                        analysis_data.append(
                            {
                                "video_url": entry["video_url"],
                                "title": video_info.get("title", ""),
                                "artist": artist,
                                "layer": layer,
                                "genre": "",
                                "downloaded": "NO",
                            }
                        )

                    except Exception as e:

                        missing_entries.append(
                            {
                                "video_url": entry["video_url"],
                                "title": video_info.get("title", "") if video_info else "",
                                "error": str(e),
                            }
                        )
        finally:
            self.progress(0, 1)

        return analysis_data, missing_entries

    def append_to_csv(self, rows):

        with self.storage.open_path(self.master_csv, "a", encoding="utf-8-sig", newline="") as f:

            writer = csv.writer(f)

            for row in rows:

                writer.writerow(
                    [
                        datetime.now().strftime("%Y-%m-%d"),
                        row["video_url"],
                        row["title"],
                        row["artist"],
                        row["layer"],
                        row["genre"],
                        row["downloaded"],
                    ]
                )

        self.log(
            f"\nAdded {len(rows)} "
            f"new {'song' if len(rows) == 1 else 'songs'} "
            "to the master CSV."
        )

    def read_csv(self):
        rows = []
        errors = []

        with self.storage.open_path(self.master_csv, "r", encoding="utf-8-sig", newline="") as f:

            reader = csv.DictReader(f)

            required = [
                "date_added",
                "video_url",
                "title",
                "artist",
                "layer",
                "genre",
                "downloaded",
            ]

            if reader.fieldnames is None:
                self.blank()
                self.log("CSV is empty.")
                return None

            if reader.fieldnames[:len(required)] != required:
                self.blank()
                self.log("CSV headers are incorrect.")
                self.log("Expected first columns:\n" + ", ".join(required))
                return None

            for row_num, row in enumerate(reader, start=2):

                cleaned_row = {}

                for key, value in row.items():

                    if value is None:
                        value = ""

                    cleaned_row[key] = value.strip()

                if not cleaned_row["date_added"]:
                    cleaned_row["date_added"] = "Unknown"

                if not cleaned_row["video_url"]:
                    errors.append(f"Row {row_num}: Video URL is blank.")

                if not cleaned_row["artist"]:
                    errors.append(f"Row {row_num}: Artist is blank.")

                if not cleaned_row["genre"]:
                    errors.append(f"Row {row_num}: Genre is blank.")

                if cleaned_row["layer"] and cleaned_row["layer"] not in (
                    "1",
                    "2",
                    "3",
                    "4",
                ):
                    errors.append(f"Row {row_num}: Layer must be blank or 1-4.")
                if cleaned_row["downloaded"] not in (
                    "YES",
                    "NO",
                ):
                    errors.append(f"Row {row_num}: Downloaded must be YES or NO.")

                rows.append(cleaned_row)

        if errors:

            self.report("CSV Validation Errors")

            for error in errors:
                self.log(error)

            return None

        return rows

    def write_csv(self, rows):

        if not rows:
            return

        temp_csv = self.storage.file("music_database.csv.tmp")

        with self.storage.open_path(
            temp_csv,
            "w",
            encoding="utf-8-sig",
            newline="",
        ) as f:

            writer = csv.writer(f)

            fixed = [
                "date_added",
                "video_url",
                "title",
                "artist",
                "layer",
                "genre",
                "downloaded",
            ]

            headers = fixed[:]

            for column in rows[0]:

                if column not in fixed:
                    headers.append(column)

            writer.writerow(headers)

            fixed = [
                "date_added",
                "video_url",
                "title",
                "artist",
                "layer",
                "genre",
                "downloaded",
            ]

            for row in rows:

                values = []

                for column in fixed:
                    values.append(row.get(column, ""))

                for column in row:

                    if column not in fixed:
                        values.append(row[column])

                writer.writerow(values)

        if self.storage.exists(self.master_csv):
            self.storage.unlink(self.master_csv)

        self.storage.rename(
            temp_csv,
            self.master_csv,
        )

    def safe_filename(self, name):
        return re.sub(r'[<>:"/\\|?*]', "_", name).strip()

    def tag_opus_file(self, file_path, row):
        audio = OggOpus(file_path)

        audio["title"] = [row["title"]]
        audio["artist"] = [row["artist"]]
        if row["layer"]:
            audio["album"] = [LAYER_NAMES[int(row["layer"])]]
        else:
            audio["album"] = ["Blank"]
        audio["genre"] = [row["genre"]]
        audio["comment"] = [row["video_url"]]

        audio.save()

    def download_track(self, row):

        filename = self.safe_filename(row["title"]) + " - " + self.safe_filename(row["artist"])

        download_path = self.storage.file(f"{filename}.opus")

        logger = DownloadLogger(self.log)

        ydl_opts = {
            "format": "bestaudio[acodec=opus]/bestaudio",
            "ffmpeg_location": self.storage.ffmpeg_location(),
            "outtmpl": str(self.storage.file(f"{filename}.%(ext)s")),
            "logger": logger,
            "writethumbnail": True,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "opus",
                },
                {
                    "key": "EmbedThumbnail",
                },
            ],
        }

        try:

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([row["video_url"]])

            self.tag_opus_file(download_path, row)

            row["downloaded"] = "YES"

            return (
                "DOWNLOADED",
                None,
            )

        except Exception as e:
            return (
                "FAILED",
                logger.last_error or str(e),
            )

    def download_pending(self, rows):

        downloaded = 0
        failed = []

        pending = []

        for row in rows:

            filename = (
                self.safe_filename(row["title"]) + " - " + self.safe_filename(row["artist"]) + ".opus"
            )

            file_path = self.storage.file(filename)

            if self.storage.exists(file_path):

                if row["downloaded"] == "NO":
                    row["downloaded"] = "YES"

                continue

            if row["downloaded"] == "YES":
                row["downloaded"] = "NO"

            pending.append(row)

        total = len(pending)

        if total == 0:
            self.blank()
            self.log("No songs need downloading.")
            return

        for index, row in enumerate(pending, start=1):

            self.progress(index, total)

            self.log(
                self.format_song(
                    "download",
                    index,
                    total,
                    row["title"],
                    row["artist"],
                )
            )

            result, error = self.download_track(row)

            if result == "DOWNLOADED":
                downloaded += 1
            else:
                failed.append(
                    {
                        "title": row["title"],
                        "error": error,
                    }
                )

        self.report("Download Complete")

        self.log(f"Downloaded: {downloaded}")
        self.blank()

        if failed:

            self.log(f"\nFailed: {len(failed)}")

            for index, item in enumerate(failed, start=1):

                self.log(
                    self.format_song(
                        "failed",
                        index,
                        len(failed),
                        item["title"],
                    )
                )

                self.log(f"    {item['error']}")

        self.write_csv(rows)

        self.progress(0, 1)

    def build_playlists(self):

        rows = self.read_csv()

        if rows is None:
            return

        playlists = {
            1: self.storage.open_path(
                self.storage.file("Dollop.m3u8"),
                "w",
                encoding="utf-8"
            ),
            2: self.storage.open_path(
                self.storage.file("Peer.m3u8"), 
                "w", 
                encoding="utf-8"
            ),
            3: self.storage.open_path(
                self.storage.file("PeerJ.m3u8"), 
                "w", 
                encoding="utf-8"
            ),
            4: self.storage.open_path(
                self.storage.file("For Dakota_ig.m3u8"), 
                "w", 
                encoding="utf-8"
            ),
        }

        try:

            for playlist in playlists.values():
                playlist.write("#EXTM3U\n")
                playlist.write("#EXTENC:UTF-8\n")

            for row in rows:

                if row["downloaded"] != "YES":
                    continue

                if not row["layer"]:
                    continue

                filename = (
                    self.safe_filename(row["title"])
                    + " - "
                    + self.safe_filename(row["artist"])
                    + ".opus"
                )

                layer = int(row["layer"])

                for playlist_layer, playlist in playlists.items():

                    if layer <= playlist_layer:
                        playlist.write(filename + "\n")

        finally:

            for playlist in playlists.values():
                playlist.close()

        self.blank()
        self.log("Playlists updated.")

    def index_library(self, rows):

        self.log("Indexing library...")

        url_to_file = {}

        duplicates_removed = 0
        deleted_titles = []

        for file in self.storage.glob("*.opus"):

            try:

                audio = OggOpus(file)

                url = audio.get("comment", [""])[0]

                if url:

                    existing = url_to_file.get(url)

                    if existing is not None:

                        existing_time = existing.stat().st_mtime
                        current_time = file.stat().st_mtime

                        if current_time > existing_time:

                            self.storage.unlink(existing)
                            duplicates_removed += 1
                            deleted_titles.append(existing.stem)

                            url_to_file[url] = file

                        else:

                            self.storage.unlink(file)
                            duplicates_removed += 1
                            deleted_titles.append(file.stem)

                    else:

                        url_to_file[url] = file

            except Exception:
                pass

        missing = 0
        missing_titles = []

        total = len(rows)

        for current, row in enumerate(rows, start=1):

            file = url_to_file.get(row["video_url"])

            if file is None:

                row["downloaded"] = "NO"

                missing += 1
                missing_titles.append(row["title"])

                continue

            row["downloaded"] = "YES"

        return (
            url_to_file,
            missing,
            missing_titles,
            duplicates_removed,
            deleted_titles,
        )

    def synchronize_library(self, rows, url_to_file):

        renamed = 0
        retagged = 0

        total = len(rows)

        try:

            for current, row in enumerate(rows, start=1):

                self.progress(current, total)

                file = url_to_file.get(row["video_url"])

                if file is None:
                    continue

                try:

                    expected_name = (
                        self.safe_filename(row["title"])
                        + " - "
                        + self.safe_filename(row["artist"])
                        + ".opus"
                    )

                    expected_path = self.storage.file(expected_name)

                    audio = OggOpus(file)

                    needs_tag = (
                        audio.get("title", [""])[0] != row["title"]
                        or audio.get("artist", [""])[0] != row["artist"]
                        or (
                            row["layer"]
                            and audio.get("album", [""])[0]
                            != LAYER_NAMES[int(row["layer"])]
                        )
                        or audio.get("genre", [""])[0] != row["genre"]
                        or audio.get("comment", [""])[0] != row["video_url"]
                    )

                    if needs_tag:

                        self.tag_opus_file(file, row)

                        retagged += 1

                    if file != expected_path:

                        if not self.storage.exists(expected_path):
                            self.storage.rename(file, expected_path)

                            renamed += 1

                            url_to_file[row["video_url"]] = expected_path

                except Exception as e:

                    self.log(
                        f"Failed to synchronize:\n"
                        f"    {row['title']}\n"
                        f"    {e}"
                    )

        finally:
            self.progress(0, 1)

        return renamed, retagged

    def csv_sync(self, download_first, prompt_if_missing=True):

        rows = self.read_csv()

        if rows is None:
            return

        if download_first:

            self.download_pending(rows)

            url_to_file, missing, missing_titles, deleted, deleted_titles = (
                self.index_library(rows)
            )

        else:

            url_to_file, missing, missing_titles, deleted, deleted_titles = (
                self.index_library(rows)
            )

            if missing and prompt_if_missing:

                return {
                    "status": "needs_download",
                    "missing": missing,
                    "missing_titles": missing_titles,
                }

        renamed, retagged = self.synchronize_library(
            rows,
            url_to_file,
        )

        self.write_csv(rows)

        self.build_playlists()

        self.report("CSV Synchronization Complete")

        printed = False

        if renamed:
            self.log(f"Renamed: {renamed}")
            printed = True

        if retagged:
            self.log(f"Retagged: {retagged}")
            printed = True

        if deleted:
            self.log(f"Deleted: {deleted}")

            for index, title in enumerate(deleted_titles, start=1):
                self.log(
                    self.format_song(
                        "missing",
                        index,
                        deleted,
                        title,
                    )
                )

            printed = True

        if missing:
            self.log(f"Missing: {missing}")

            for index, title in enumerate(missing_titles, start=1):
                self.log(
                    self.format_song(
                        "missing",
                        index,
                        missing,
                        title,
                    )
                )

            printed = True

        if not printed:
            self.log("No changes.")

        self.blank()
        self.log("Finished.")

    def analyze_playlist(self, url, layer=""):

        url = self.normalize_playlist_url(url)

        try:

            info = self.get_playlist_info(url)

            new_entries, _ = self.filter_duplicates(info["entries"])

            if not new_entries:

                self.log(
                    "\nAll songs in this playlist are already present " "in the master CSV."
                )

                return {"status": "up_to_date"}

            analysis_data, missing_entries = self.analyze_entries(
                new_entries,
                layer,
            )

            if missing_entries:

                self.report("Missing Videos Found")

                for i, entry in enumerate(missing_entries, start=1):
                    self.log(
                        self.format_song(
                            "missing_video",
                            i,
                            len(missing_entries),
                            entry["title"],
                        )
                    )
                    self.log(f"    {entry['video_url']}")
                    self.log(f"    {entry['error']}\n")

                self.log(f"Total Missing: {len(missing_entries)}")

                return {
                    "status": "missing_videos",
                    "missing_entries": missing_entries,
                }

            self.blank()
            self.log("Analysis complete.")

            self.append_to_csv(analysis_data)

            return {"status": "csv_ready"}

        except Exception as e:

            self.log(f"\nError: {e}")

            return {"status": "error"}

    def finish_playlist_processing(self):

        rows = self.read_csv()

        if rows is None:
            return False

        self.download_pending(rows)

        self.build_playlists()

        return True
