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
from kivy.utils import platform
import traceback
from threading import Timer, Event
from time import monotonic

import ssl
import certifi

import json
import math
import subprocess

from contextlib import ExitStack

ssl._create_default_https_context = lambda: ssl.create_default_context(
    cafile=certifi.where()
)

ADB_REPORT_MODE = False

NORMALIZATION_TARGET_LUFS = -23.0
NORMALIZATION_MIN_GAIN_DB = -12.0
NORMALIZATION_MAX_GAIN_DB = 3.0
NORMALIZATION_PEAK_DBTP = -1.0
POWERAMP_GAIN_OFFSET_DB = 5.0

class SilentLogger:
    def debug(self, msg):
        if ADB_REPORT_MODE:
            print(msg, flush=True)

    def warning(self, msg):
        if "No supported JavaScript runtime could be found" in msg:
            return
        if ADB_REPORT_MODE:
            print(msg, flush=True)

    def error(self, msg):
        if ADB_REPORT_MODE:
            print(msg, flush=True)

class DownloadLogger:
    def __init__(self, log):
        self.last_error = None
        self.log = log

    def debug(self, msg):
        if ADB_REPORT_MODE:
            print(msg, flush=True)

    def warning(self, msg):
        if ADB_REPORT_MODE:
            print(msg, flush=True)

    def error(self, msg):
        self.last_error = msg
        if ADB_REPORT_MODE:
            print(msg, flush=True)

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
            from jnius import autoclass

            activity = autoclass("org.kivy.android.PythonActivity").mActivity
            native_dir = Path(activity.getApplicationInfo().nativeLibraryDir)
            return str(native_dir / "libffmpeg.so")

        return str(
            Path(__file__).resolve().parent
            / "ffmpeg"
            / "windows"
        )

class LibraryMachine:

    def __init__(
        self,
        library_path,
        log_callback=None,
        progress_callback=None,
        layer_settings_path=None,
    ):

        if isinstance(library_path, PathStorage):
            self.storage = library_path
        else:
            self.storage = PathStorage(library_path)
        self.library_path = self.storage.root

        if platform == "android":
            from android_node import configure

            self.js_runtimes = configure()
        else:
            self.js_runtimes = {"node": {}}

        self.master_csv = self.storage.file("music_database.csv")

        self.log = log_callback or (lambda msg="": None)
        self.progress = progress_callback or (lambda c, t: None)

        self.hrr = "================================"
        self.hr = "---------------------------"

        if layer_settings_path is None:
            raise ValueError("A writable layer settings path is required.")

        self.layers_file = Path(layer_settings_path)
        self.default_layer_names = self.read_default_layers()
        self.layer_names = dict(self.default_layer_names)

        # Historical filenames: used only to clean up old generated playlists.
        self.layer_playlist_files = [
            "Dollop.m3u8",
            "Peer.m3u8",
            "PeerJ.m3u8",
            "For Dakota_ig.m3u8",
        ]

        if self.layers_file.exists():
            settings = json.loads(
                self.layers_file.read_text(encoding="utf-8")
            )

            self.layer_names.update({
                int(layer): name
                for layer, name in settings["names"].items()
            })
            self.layer_playlist_files = settings["playlist_files"]

            if any(
                not isinstance(name, str)
                or "/" in name
                or "\\" in name
                or not name.endswith(".m3u8")
                for name in self.layer_playlist_files
            ):
                raise ValueError("Invalid playlist filenames in layer settings")

            if any(layer < 1 for layer in self.layer_names):
                raise ValueError("Layer numbers must be positive")

        self.validate_layer_names(self.layer_names)
        self.ensure_layers(max(self.layer_names))

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
                "verbose": ADB_REPORT_MODE,
                "quiet": not ADB_REPORT_MODE,
                "no_warnings": not ADB_REPORT_MODE,
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
                        traceback.print_exc()

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

        try:
            f = self.storage.open_path(
                self.master_csv, "r", encoding="utf-8-sig", newline=""
            )
        except FileNotFoundError:
            traceback.print_exc()
            self.blank()
            if platform == "win":
                self.log("Windows path error. See terminal for details")
            else:
                self.log("Android path error. See ADB for details")
            return None

        with f:
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

                layer_text = cleaned_row["layer"]

                if layer_text:
                    if (
                        not re.fullmatch(r"[0-9]+", layer_text)
                        or int(layer_text) < 1
                    ):
                        errors.append(
                            f"Row {row_num}: Layer must be blank "
                            "or a positive whole number."
                        )
                    else:
                        cleaned_row["layer"] = str(int(layer_text))
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

        highest = max(
            (int(row["layer"]) for row in rows if row["layer"]),
            default=0,
        )

        self.ensure_layers(highest)

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

    def read_default_layers(self):
        path = Path(__file__).resolve().parent / "layers.txt"
        names = {}

        lines = path.read_text(encoding="utf-8-sig").splitlines()

        for line_number, line in enumerate(lines, start=1):
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            number, separator, name = line.partition("=")
            number = number.strip()
            name = name.strip()

            if (
                not separator
                or not re.fullmatch(r"[0-9]+", number)
                or int(number) < 1
            ):
                raise ValueError(
                    f"layers.txt line {line_number}: expected number=name"
                )

            layer = int(number)

            if layer in names:
                raise ValueError(
                    f"layers.txt: layer {layer} appears more than once"
                )

            names[layer] = name

        if not names:
            raise ValueError("layers.txt must contain at least one layer")

        self.validate_layer_names(names)
        return names

    def layer_playlist_filename(self, layer, name):
        return self.safe_filename(name).rstrip(". ") + ".m3u8"

    def validate_layer_names(self, names):
        filenames = set()

        reserved = {"CON", "PRN", "AUX", "NUL"}
        reserved.update(
            f"{prefix}{number}"
            for prefix in ("COM", "LPT")
            for number in range(1, 10)
        )

        for layer, name in names.items():
            if (
                not isinstance(name, str)
                or not name
                or any(ord(char) < 32 for char in name)
            ):
                raise ValueError(
                    f"Layer {layer}: enter a nonempty, single-line name."
                )

            stem = self.safe_filename(name).rstrip(". ")

            if not stem or stem.split(".")[0].upper() in reserved:
                raise ValueError(
                    f"Layer {layer}: this name cannot be used as a filename."
                )

            filename = self.layer_playlist_filename(layer, name).casefold()

            if filename in filenames:
                raise ValueError(
                    "Each layer needs a different playlist filename."
                )

            filenames.add(filename)

    def save_layers(self):
        self.layers_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.layers_file.with_suffix(".json.tmp")

        # Save only renamed layers and layers absent from the bundled defaults.
        overrides = {
            layer: name
            for layer, name in self.layer_names.items()
            if self.default_layer_names.get(layer) != name
        }

        temporary.write_text(
            json.dumps(
                {
                    "names": overrides,
                    "playlist_files": self.layer_playlist_files,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        temporary.replace(self.layers_file)

    def ensure_layers(self, highest):
        names = dict(self.layer_names)

        for layer in range(1, highest + 1):
            if layer in names:
                continue

            name = f"Layer {layer}"

            used = {
                self.layer_playlist_filename(number, value).casefold()
                for number, value in names.items()
            }

            while self.layer_playlist_filename(layer, name).casefold() in used:
                name += "_"

            names[layer] = name

        if names != self.layer_names:
            self.validate_layer_names(names)

            previous = self.layer_names
            self.layer_names = names

            try:
                self.save_layers()
            except Exception:
                self.layer_names = previous
                raise

    def rename_layers(self, names):
        names = {
            layer: name.strip()
            for layer, name in names.items()
        }

        if not set(self.layer_names).issubset(names):
            raise ValueError(
                "The layer list changed. Close and reopen the editor."
            )

        if set(names) != set(range(1, max(names) + 1)):
            raise ValueError("Layer numbers must be consecutive, starting at 1.")

        self.validate_layer_names(names)

        previous = self.layer_names
        self.layer_names = names

        try:
            self.save_layers()
        except Exception:
            self.layer_names = previous
            raise

    def tag_opus_file(self, file_path, row):
        audio = OggOpus(file_path)

        audio["title"] = [row["title"]]
        audio["artist"] = [row["artist"]]
        if row["layer"]:
            audio["album"] = [self.layer_names[int(row["layer"])]]
        else:
            audio["album"] = ["Blank"]
        audio["genre"] = [row["genre"]]
        audio["comment"] = [row["video_url"]]

        audio.save()

    def calculate_normalization_gain(self, file_path):
        ffmpeg = Path(self.storage.ffmpeg_location())

        if ffmpeg.is_dir():
            ffmpeg = ffmpeg / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")

        result = subprocess.run(
            [
                str(ffmpeg),
                "-hide_banner",
                "-nostdin",
                "-nostats",
                "-loglevel",
                "info",
                "-i",
                str(file_path),
                "-map",
                "0:a:0",
                "-vn",
                "-sn",
                "-dn",
                "-af",
                "loudnorm=I=-23:TP=-1:LRA=50:print_format=json",
                "-f",
                "null",
                "-",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        if ADB_REPORT_MODE:
            print(result.stderr, flush=True)

        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg loudness scan failed:\n{result.stderr[-1500:]}")

        summaries = re.findall(
            r'\{[^{}]*"input_i"[^{}]*\}',
            result.stderr,
        )

        if not summaries:
            raise RuntimeError("FFmpeg did not return a loudness measurement.")

        measurements = json.loads(summaries[-1])
        loudness = float(measurements["input_i"])
        true_peak = float(measurements["input_tp"])

        if not math.isfinite(loudness) or not math.isfinite(true_peak):
            raise ValueError("No measurable loudness; the track may be silent.")

        requested_gain = NORMALIZATION_TARGET_LUFS - loudness

        limited_gain = min(
            NORMALIZATION_MAX_GAIN_DB,
            max(NORMALIZATION_MIN_GAIN_DB, requested_gain),
        )

        peak_limit = NORMALIZATION_PEAK_DBTP - true_peak - POWERAMP_GAIN_OFFSET_DB

        if peak_limit < NORMALIZATION_MIN_GAIN_DB:
            raise ValueError(
                "Peak protection would exceed the allowed volume reduction."
            )

        gain = math.floor(min(limited_gain, peak_limit) * 256)

        if not -32768 <= gain <= 32767:
            raise ValueError("Calculated gain is outside the Opus tag range.")

        if ADB_REPORT_MODE:
            print(
                f"Loudness: {loudness:.2f} LUFS; "
                f"peak: {true_peak:.2f} dBTP; "
                f"R128 gain: {gain / 256:+.2f} dB",
                flush=True,
            )

        return gain

    def write_normalization_tag(self, file_path, gain):
        if type(gain) is not int or not -32768 <= gain <= 32767:
            raise ValueError("Invalid Opus normalization gain.")

        audio = OggOpus(file_path)
        audio["R128_TRACK_GAIN"] = [str(gain)]
        audio.save()

    def normalize_files(self):
        rows = self.read_csv()

        if rows is None:
            self.log("Normalization skipped: correct the CSV errors first.")
            return

        ready_rows = {
            row["video_url"]: row
            for row in rows
            if row["downloaded"] == "YES"
        }

        files = sorted(self.storage.glob("*.opus"))

        tagged = 0
        skipped = 0
        not_ready = 0
        failed = 0

        self.major("Analyzing loudness...")
        self.progress(0, 1)

        try:
            for current, file in enumerate(files, start=1):
                try:
                    audio = OggOpus(file)

                    row = ready_rows.get(
                        audio.get("comment", [""])[0]
                    )

                    if row is None:
                        not_ready += 1
                        continue

                    expected = {
                        "title": row["title"],
                        "artist": row["artist"],
                        "album": (
                            self.layer_names[int(row["layer"])]
                            if row["layer"]
                            else "Blank"
                        ),
                        "genre": row["genre"],
                        "comment": row["video_url"],
                    }

                    if any(
                        key not in audio or audio[key] != [value]
                        for key, value in expected.items()
                    ):
                        not_ready += 1
                        continue

                    values = audio.get("R128_TRACK_GAIN", [])

                    if (
                        len(values) == 1
                        and len(values[0]) <= 6
                        and re.fullmatch(r"[+-]?[0-9]+", values[0])
                        and -32768 <= int(values[0]) <= 32767
                    ):
                        skipped += 1
                        continue

                    self.log(f"Analyzing: {file.stem}")

                    gain = self.calculate_normalization_gain(file)
                    self.write_normalization_tag(file, gain)

                    tagged += 1

                except Exception as exc:
                    failed += 1

                    if ADB_REPORT_MODE:
                        traceback.print_exc()

                    self.log(
                        f"Normalization failed:\n"
                        f"    {file.name}\n"
                        f"    {exc}"
                    )

                finally:
                    self.progress(current, len(files))

        finally:
            self.progress(0, 1)

        self.report("Normalization Complete")
        self.log(f"Tagged: {tagged}")
        self.log(f"Already tagged: {skipped}")
        self.log(f"Skipped (download/metadata incomplete): {not_ready}")
        self.log(f"Failed: {failed}")

    def download_track(self, row):

        filename = self.safe_filename(row["title"]) + " - " + self.safe_filename(row["artist"])

        download_path = self.storage.file(f"{filename}.opus")

        logger = DownloadLogger(self.log)

        ydl_opts = {
            "format": "bestaudio[acodec=opus]/bestaudio",
            "ffmpeg_location": self.storage.ffmpeg_location(),
            "outtmpl": str(self.storage.file(f"{filename}.%(ext)s")),
            "logger": logger,
            "verbose": ADB_REPORT_MODE,
            "quiet": not ADB_REPORT_MODE,
            "writethumbnail": True,
            "js_runtimes": self.js_runtimes,
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
            if not isinstance(e, yt_dlp.utils.DownloadError):
                traceback.print_exc()
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

        names = dict(self.layer_names)
        self.validate_layer_names(names)

        filenames = {
            layer: self.layer_playlist_filename(layer, name)
            for layer, name in sorted(names.items())
        }

        previous_files = set(self.layer_playlist_files)

        for filename in filenames.values():
            path = self.storage.file(filename)

            if path.exists() and filename not in previous_files:
                same_managed_file = any(
                    self.storage.file(old).exists()
                    and path.samefile(self.storage.file(old))
                    for old in previous_files
                )

                if not same_managed_file:
                    raise ValueError(
                        "Playlist already exists and is not managed "
                        f"by the app: {filename}"
                    )

        with ExitStack() as stack:
            playlists = {
                layer: stack.enter_context(
                    self.storage.open_path(
                        self.storage.file(filename + ".tmp"),
                        "w",
                        encoding="utf-8",
                    )
                )
                for layer, filename in filenames.items()
            }

            for playlist in playlists.values():
                playlist.write("#EXTM3U\n#EXTENC:UTF-8\n")

            for row in rows:
                if row["downloaded"] != "YES" or not row["layer"]:
                    continue

                filename = (
                    self.safe_filename(row["title"])
                    + " - "
                    + self.safe_filename(row["artist"])
                    + ".opus"
                )

                for layer, playlist in playlists.items():
                    if int(row["layer"]) <= layer:
                        playlist.write(filename + "\n")

        # Retain both sets so an interrupted rebuild can retry.
        self.layer_playlist_files = sorted(
            previous_files | set(filenames.values())
        )
        self.save_layers()

        for filename in filenames.values():
            self.storage.file(filename + ".tmp").replace(
                self.storage.file(filename)
            )

        current_files = set(filenames.values())

        for filename in previous_files - current_files:
            path = self.storage.file(filename)

            if path.exists() and not any(
                path.samefile(self.storage.file(current))
                for current in current_files
            ):
                self.storage.unlink(path)

        self.layer_playlist_files = list(filenames.values())
        self.save_layers()

        self.blank()
        self.log("Playlists updated.")

    def index_library(self, rows):

        self.log("Indexing library...")

        url_to_file = {}

        duplicates_removed = 0
        deleted_titles = []

        valid_urls = {row["video_url"] for row in rows if row["video_url"]}

        for file in self.storage.glob("*.opus"):

            try:

                audio = OggOpus(file)

                url = audio.get("comment", [""])[0]

                if url not in valid_urls:
                    self.storage.unlink(file)
                    duplicates_removed += 1
                    deleted_titles.append(file.stem)
                    continue

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

                    expected_album = (
                        self.layer_names[int(row["layer"])]
                        if row["layer"]
                        else "Blank"
                    )

                    needs_tag = (
                        audio.get("title", [""])[0] != row["title"]
                        or audio.get("artist", [""])[0] != row["artist"]
                        or audio.get("album", [""])[0] != expected_album
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
                    traceback.print_exc()

                    self.log(
                        f"Failed to synchronize:\n"
                        f"    {row['title']}\n"
                        f"    {e}"
                    )

        finally:
            self.progress(0, 1)

        return renamed, retagged

    def csv_sync(self, download_first, prompt_if_missing=True):

        read_started = monotonic()

        def reading_notice_callback():
            elapsed = monotonic() - read_started
            print(f"SYNC: timer fired at {elapsed:.3f}s", flush=True)
            self.log("Reading CSV...")
            print("SYNC: reading message queued", flush=True)

        reading_notice = Timer(3.0, reading_notice_callback)
        reading_notice.daemon = True
        reading_notice.start()

        try:
            rows = self.read_csv()
        finally:
            elapsed = monotonic() - read_started
            print(f"SYNC: cancelling timer at {elapsed:.3f}s", flush=True)
            reading_notice.cancel()

        if elapsed > 3.0:
            self.log("CSV Read Complete.")

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

        self.normalize_files()

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
            traceback.print_exc()

            self.log(f"\nError: {e}")

            return {"status": "error"}

    def finish_playlist_processing(self):
        rows = self.read_csv()

        if rows is None:
            return False

        self.download_pending(rows)
        self.build_playlists()
        self.normalize_files()

        return True
