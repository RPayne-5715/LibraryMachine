from pathlib import Path
import yt_dlp
from urllib.parse import urlparse, parse_qs
import csv
import re
from mutagen.oggopus import OggOpus

import sys

sys.path.insert(0, str(Path(__file__).parent / "vendor"))

from pytubefix import Playlist

LAYER_NAMES = {
    1: "Dollop",
    2: "Peer",
    3: "PeerJ",
    4: "For Dakota ig",
}

PLAYLIST_URLS = {
    1: "https://music.youtube.com/playlist?list=PLb4_zdQ6SjIB7NW7YYprjrTgBwCzbA38q",
    2: "https://music.youtube.com/playlist?list=PLb4_zdQ6SjIApWHLrRZ3QXFmlUD3_mmKm",
    3: "https://music.youtube.com/playlist?list=PLb4_zdQ6SjID2jMAqjdZhf3KEws3Xw1HI",
    4: "https://music.youtube.com/playlist?list=PLb4_zdQ6SjIAd8zgUu_VKpwGAPaO0iNnW",
}

class SilentLogger:
    def debug(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        pass

class DownloadLogger:

    def __init__(self):
        self.last_error = None

    def debug(self, msg):
        pass

    def warning(self, msg):
        if "No supported JavaScript runtime could be found" in msg:
            return

        self.log(f"WARNING: {msg}")

    def error(self, msg):
        self.last_error = msg

def progress(current, total):
    pass

class LibraryMachine:
    hr = "==========================="
    hrr = "---------------------------"
    def __init__(
            self, 
            library_path,
            log_callback=None, 
            progress_callback=None
        ):
        self.app_path = Path(__file__).resolve().parent
        self.library_path = Path(library_path)

        self.master_csv = self.app_path / "music_database.csv"

        self.log = log_callback or (lambda msg="": None)
        self.progress = progress_callback or (lambda c, t: None)

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
            self.log("\nMaster CSV not found. Creating CSV...")
            with open(self.master_csv, "w", encoding="utf-8-sig", newline="") as f:

                writer = csv.writer(f)

                writer.writerow(
                    [
                        "video_url",
                        "title",
                        "artist",
                        "layer",
                        "downloaded",
                    ]
                )

            return entries, False

        existing_urls = set()

        with open(self.master_csv, "r", encoding="utf-8-sig", newline="") as f:

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

        with open(self.master_csv, "a", encoding="utf-8-sig", newline="") as f:

            writer = csv.writer(f)

            for row in rows:

                writer.writerow(
                    [
                        row["video_url"],
                        row["title"],
                        row["artist"],
                        row["layer"],
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

        with open(self.master_csv, "r", encoding="utf-8-sig", newline="") as f:

            reader = csv.DictReader(f)

            required = [
                "video_url",
                "title",
                "artist",
                "layer",
                "downloaded",
            ]

            if reader.fieldnames != required:
                self.log("\nCSV headers are incorrect.")
                self.log("Expected:\n" + ", ".join(required))
                return None

            for row_num, row in enumerate(reader, start=2):

                cleaned_row = {}

                for key, value in row.items():
                    cleaned_row[key] = value.strip()

                if not cleaned_row["video_url"]:
                    errors.append(f"Row {row_num}: Video URL is blank.")

                if not cleaned_row["artist"]:
                    errors.append(f"Row {row_num}: Artist is blank.")

                if cleaned_row["layer"] not in (
                    "1",
                    "2",
                    "3",
                    "4",
                ):
                    errors.append(f"Row {row_num}: Layer must be 1-4.")

                if cleaned_row["downloaded"] not in (
                    "YES",
                    "NO",
                ):
                    errors.append(f"Row {row_num}: Downloaded must be YES or NO.")

                rows.append(cleaned_row)

        if errors:

            self.log("")
            self.log(self.hrr)
            self.log("CSV Validation Errors")
            self.log(self.hrr)
            self.log("")

            for error in errors:
                self.log(error)

            return None

        return rows

    def safe_filename(self, name):
        return re.sub(r'[<>:"/\\|?*]', "_", name).strip()

    def tag_opus_file(self, file_path, row):
        audio = OggOpus(file_path)

        audio["title"] = [row["title"]]
        audio["artist"] = [row["artist"]]
        audio["album"] = [LAYER_NAMES[int(row["layer"])]]
        audio["comment"] = [row["video_url"]]

        audio.save()

    def download_track(self, row):

        filename = self.safe_filename(row["title"]) + " - " + self.safe_filename(row["artist"])

        download_path = self.library_path / f"{filename}.opus"

        logger = DownloadLogger()

        ydl_opts = {
            "format": "bestaudio[acodec=opus]/bestaudio",
            "ffmpeg_location": str(self.library_path / "ffmpeg"),
            "outtmpl": str(self.library_path / f"{filename}.%(ext)s"),
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

            file_path = self.library_path / filename

            if file_path.exists():

                if row["downloaded"] == "NO":
                    row["downloaded"] = "YES"

                continue

            if row["downloaded"] == "YES":
                row["downloaded"] = "NO"

            pending.append(row)

        total = len(pending)

        if total == 0:
            self.log("\nNo songs need downloading.")
            return

        for index, row in enumerate(pending, start=1):

            self.log(
                f"({index}/{total}) " f"{row['title']} - {row['artist']}",
                flush=True,
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

        self.log("")
        self.log(self.hrr)
        self.log("Download Complete")
        self.log(self.hrr)

        self.log(f"\nDownloaded: {downloaded}")

        if failed:

            self.log(f"\nFailed: {len(failed)}")

            for item in failed:
                self.log(f"  - {item['title']}")
                self.log(f"    {item['error']}")

        with open(self.master_csv, "w", encoding="utf-8-sig", newline="") as f:

            writer = csv.writer(f)

            writer.writerow(
                [
                    "video_url",
                    "title",
                    "artist",
                    "layer",
                    "downloaded",
                ]
            )

            for row in rows:

                writer.writerow(
                    [
                        row["video_url"],
                        row["title"],
                        row["artist"],
                        row["layer"],
                        row["downloaded"],
                    ]
                )

    def build_playlists(self):

        rows = self.read_csv()

        if rows is None:
            return

        playlists = {
            1: open(self.library_path / "Dollop.m3u", "w", encoding="utf-8"),
            2: open(self.library_path / "Peer.m3u", "w", encoding="utf-8"),
            3: open(self.library_path / "PeerJ.m3u", "w", encoding="utf-8"),
            4: open(self.library_path / "For Dakota ig.m3u", "w", encoding="utf-8"),
        }

        try:

            for playlist in playlists.values():
                playlist.write("#EXTM3U\n")

            for row in rows:

                if row["downloaded"] != "YES":
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

        self.log("\nPlaylists updated.")

    def needs_download_before_sync(self):
        rows = self.read_csv()

        if rows is None:
            return False

        return any(row["downloaded"] == "NO" for row in rows)

    def csv_sync(self, download_first):
        try:
            rows = self.read_csv()

            if rows is None:
                return

            pending = any(row["downloaded"] == "NO" for row in rows)

            if pending:

                self.log("\nUndownloaded songs detected.")

                if download_first:

                    self.download_pending(rows)

                    rows = self.read_csv()

                    if rows is None:
                        return
            self.log(self.hr)
            self.log("\nIndexing library...")

            url_to_file = {}

            for file in self.library_path.glob("*.opus"):

                try:

                    audio = OggOpus(file)

                    url = audio.get("comment", [""])[0]

                    if url:
                        url_to_file[url] = file

                except Exception:
                    pass

            renamed = 0
            retagged = 0
            missing = 0

            total = len(rows)

            for current, row in enumerate(rows, start=1):

                self.progress(current, total)
                file = url_to_file.get(row["video_url"])

                if file is None:

                    self.log(f"\nMissing: {row['title']}")

                    row["downloaded"] = "NO"
                    missing += 1
                    continue

                row["downloaded"] = "YES"

                expected_name = (
                    self.safe_filename(row["title"]) + " - " + self.safe_filename(row["artist"]) + ".opus"
                )

                expected_path = self.library_path / expected_name

                audio = OggOpus(file)

                needs_tag = (
                    audio.get("title", [""])[0] != row["title"]
                    or audio.get("artist", [""])[0] != row["artist"]
                    or audio.get("album", [""])[0] != LAYER_NAMES[int(row["layer"])]
                    or audio.get("comment", [""])[0] != row["video_url"]
                )

                if needs_tag:

                    self.tag_opus_file(
                        file,
                        row,
                    )

                    retagged += 1

                if file != expected_path:

                    if not expected_path.exists():
                        file.rename(expected_path)

                    renamed += 1

                    url_to_file[row["video_url"]] = expected_path

            with open(self.master_csv, "w", encoding="utf-8-sig", newline="") as f:

                writer = csv.writer(f)

                writer.writerow(
                    [
                        "video_url",
                        "title",
                        "artist",
                        "layer",
                        "downloaded",
                    ]
                )

                for row in rows:

                    writer.writerow(
                        [
                            row["video_url"],
                            row["title"],
                            row["artist"],
                            row["layer"],
                            row["downloaded"],
                        ]
                    )

            self.build_playlists()

            self.log("")
            self.log(self.hrr)
            self.log("CSV Synchronization Complete")
            self.log(self.hrr)

            self.log(f"\nRenamed: {renamed}")
            self.log(f"Retagged: {retagged}")

            if missing:

                self.log(f"Missing: {missing}")

            self.log("\nFinished.")
            self.log("")
        finally:
            self.progress(0, 1)

    def analyze_playlist(self, url):

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
                new_entries
            )

            if missing_entries:

                self.log("")
                self.log(self.hrr)
                self.log("Missing Videos Found")
                self.log(self.hrr)
                self.log("")

                for i, entry in enumerate(missing_entries, start=1):
                    self.log(f"{i}. {entry['title']}")
                    self.log(f"    {entry['video_url']}")
                    self.log(f"    {entry['error']}\n")

                self.log(f"Total Missing: {len(missing_entries)}")

                return {
                    "status": "missing_videos",
                    "missing_entries": missing_entries,
                }

            self.log("\nAnalysis complete.")

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
