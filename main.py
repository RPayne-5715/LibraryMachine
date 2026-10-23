from kivy.app import App
from kivy.animation import Animation
from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.properties import NumericProperty, StringProperty, BooleanProperty
from kivy.storage.jsonstore import JsonStore
from kivy.uix.screenmanager import ScreenManager, FadeTransition, Screen
from kivy.uix.widget import Widget
from kivy.utils import platform
from kivy.core.clipboard import Clipboard

from backend import LibraryMachine, PathStorage
from pathlib import Path
from datetime import datetime
from threading import Thread
import traceback

LIBRARY_FOLDER_NAME = "PlaylistLibrary"

FOLDER_REQUEST = 2001

__version__ = "0.20"

if platform == "android":
    from jnius import autoclass
    from android import activity

    Intent = autoclass("android.content.Intent")
    Uri = autoclass("android.net.Uri")

    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    Environment = autoclass("android.os.Environment")
    Settings = autoclass("android.provider.Settings")

    LIBRARY_ROOT = Path("/storage/emulated/0/Music")

else:
    Window.size = (412, 750)
    # 412, 915
    LIBRARY_ROOT = Path(__file__).resolve().parent.parent.parent

LIBRARY_PATH = LIBRARY_ROOT / LIBRARY_FOLDER_NAME

gradient = CoreImage("assets/progress_gradient.png").texture
gradient.wrap = "clamp_to_edge"
gradient.mag_filter = "linear"
gradient.min_filter = "linear"
CONSOLE_PADDING = 19
Window.clearcolor = (
    0x1C / 255,
    0x1C / 255,
    0x1C / 255,
    1,
)

LabelBase.register(
    name="Console",
    fn_regular="assets/CourierPrime-Regular.ttf",
)

LabelBase.register(
    name="Jua",
    fn_regular="assets/Jua-Regular.ttf",
)

def log(message=""):

    def update(dt):

        app = App.get_running_app()

        main = app.root.get_screen("main")

        console = main.ids.console
        scroll = main.ids.console_scroll

        console.text += message + "\n"

        console.height = console.minimum_height
        console.cursor = console.get_cursor_from_index(len(console.text))
        scroll.scroll_y = 0

    Clock.schedule_once(update, 0)

class Root(ScreenManager):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.transition = FadeTransition(duration=0.4)

class SplashScreen(Screen):
    pass

class MainScreen(Screen):
    progress_text = StringProperty("0/0")

class ProgressBarWidget(Widget):
    progress_amt = NumericProperty(0.0)
    fill_width = NumericProperty(0.0)
    show_fill = BooleanProperty(False)

    def on_progress_amt(self, *_):
        self.fill_width = self.width * self.progress_amt
        self.show_fill = self.progress_amt > 0

    def on_size(self, *_):
        self.fill_width = self.width * self.progress_amt

class LibraryMachineApp(App):
    gradient = gradient

    def build(self):
        self.machine = None

        self.pending_action = None
        self.current_playlist_url = None

        self.folder_uri = None
        self.store = JsonStore(str(Path(self.user_data_dir) / "settings.json"))

        return None

    def create_machine(self, library_path):

        self.machine = LibraryMachine(
            library_path=library_path,
            log_callback=log,
            progress_callback=self.update_progress,
        )

    def initialize_library(self):

        library_folder = LIBRARY_PATH
        library_folder.mkdir(parents=True, exist_ok=True)

        try:
            test = library_folder / ".write_test"
            test.write_text("")
            test.unlink()
        except Exception as e:
            traceback.print_exc()
            return

        self.create_machine(
            PathStorage(library_folder)
        )

    def on_start(self):
        if platform == "android":

            android_activity = PythonActivity.mActivity

            if not Environment.isExternalStorageManager():

                intent = Intent(
                    Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION
                )

                intent.setData(
                    Uri.parse(
                        "package:" + android_activity.getPackageName()
                    )
                )

                try:
                    android_activity.startActivity(intent)
                    return
                except Exception as e:
                    traceback.print_exc()

        self.initialize_library()

        if platform == "android":

            activity.bind(on_activity_result=self.activity_result)

            if self.store.exists("folder"):

                self.folder_uri = Uri.parse(
                    self.store.get("folder")["uri"]
                )

                self.machine.log("Folder restored.")
                self.machine.log(self.folder_uri.toString())

        Clock.schedule_once(
            self.finish_loading,
            3,
        )

    def on_pause(self):
        return True

    def on_resume(self):

        if platform != "android":
            return

        if self.machine is not None:
            return

        if not Environment.isExternalStorageManager():
            return

        self.initialize_library()

        self.finish_loading(0)

    def on_stop(self):
        if platform == "android":
            activity.unbind(on_activity_result=self.activity_result)

    def finish_loading(self, dt):

        splash = self.root.get_screen(
            "splash"
        )

        anim = Animation(
            opacity=0,
            duration=.4,
        )

        def switch(*_):

            self.root.current = "main"

            main = self.root.get_screen("main")

            main.ids.console.text = (
                "\n" * CONSOLE_PADDING
            )
            self.machine.log("~ Library Machine ~")
            self.machine.log(f"v{__version__}")

            main = self.root.get_screen("main")

        anim.bind(on_complete=switch)
        anim.start(splash)

    def save_console_log(self):

        console = self.root.get_screen("main").ids.console

        documents = Path(App.get_running_app().user_data_dir)

        filename = (
            "LibraryMachineLog_" + datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".txt"
        )

        path = documents / filename

        path.write_text(
            console.text.lstrip("\n"),
            encoding="utf-8",
        )

        self.machine.log(f"Saved log to {filename}")

        return path

    def update_progress(self, current, total):

        progress = current / total

        def update(dt):

            main = self.root.get_screen("main")

            main.ids.progress.progress_amt = progress

            if progress == 0:
                main.progress_text = "0/0"
            else:
                main.progress_text = f"{current}/{total}"

        Clock.schedule_once(update, 0)

    #

    def set_button_state(self, state):

        main = self.root.get_screen("main")

        layouts = {
            "paste": main.ids.paste_buttons,
            "yesno": main.ids.yesno_buttons,
            "continue": main.ids.continue_buttons,
            "idle": main.ids.idle_buttons,
        }

        for layout in layouts.values():
            layout.opacity = 0
            layout.disabled = True
            layout.size_hint_y = None
            layout.height = 0

        layout = layouts[state]
        layout.opacity = 1
        layout.disabled = False
        layout.size_hint_y = 1

    def yes_pressed(self):

        if self.pending_action == "sync_download":

            self.set_button_state("idle")

            Thread(
                target=lambda: self.machine.csv_sync(
                    True,
                    False,
                ),
                daemon=True,
            ).start()

            self.pending_action = None

    def no_pressed(self):

        if self.pending_action == "sync_download":

            self.set_button_state("idle")

            Thread(
                target=lambda: self.machine.csv_sync(
                    False,
                    False,
                ),
                daemon=True,
            ).start()

            self.pending_action = None

    def continue_pressed(self):

        if self.pending_action == "retry_playlist":

            self.machine.log("Analyzing playlist...")

            self.set_button_state("idle")

            Thread(
                target=self.analyze_playlist_thread,
                daemon=True,
            ).start()

        elif self.pending_action == "csv_finish":

            self.machine.major("Downloading songs...")

            self.set_button_state("idle")

            Thread(
                target=self.finish_playlist_thread,
                daemon=True,
            ).start()

        self.pending_action = None

    #

    def activity_result(self, request_code, result_code, intent):
        if request_code != FOLDER_REQUEST:
            return

        if result_code != -1 or intent is None:  # RESULT_OK
            return

        uri = intent.getData()
        if uri is None:
            return

        android_activity = PythonActivity.mActivity

        flags = intent.getFlags() & (
            Intent.FLAG_GRANT_READ_URI_PERMISSION
            | Intent.FLAG_GRANT_WRITE_URI_PERMISSION
        )

        try:
            android_activity.getContentResolver().takePersistableUriPermission(
                uri, flags
            )
        except Exception as e:
            self.machine.log(f"Could not retain folder permission: {e}")
            return

        self.folder_uri = uri
        self.store.put("folder", uri=uri.toString())

        self.machine.log("Folder saved.")
        self.machine.log(uri.toString())

    #

    def csv_pressed(self):

        if platform != "android":
            import os

            os.startfile(self.machine.master_csv)
            return

        if not self.machine.master_csv.exists():
            self.machine.blank()
            self.machine.log("music_database.csv does not exist.")
            self.machine.log("Analyze a playlist first.")
            return

        Intent = autoclass("android.content.Intent")

        intent = Intent(Intent.ACTION_VIEW)
        intent.setType("text/csv")

        try:
            PythonActivity.mActivity.startActivity(intent)
        except Exception:
            self.disable_button(
                "csv_button",
                "CSVLabs not installed."
            )

    def sync_csv_pressed(self):

        self.machine.major()

        self.set_button_state("idle")

        Thread(
            target=self.sync_csv_thread,
            daemon=True,
        ).start()

    def playlist_pressed(self):
        self.machine.major("Paste your YouTube playlist URL.")
        self.current_playlist_url = None
        self.set_button_state("paste")

    def disable_button(self, button_id, message):

        main = self.root.get_screen("main")

        button = main.ids[button_id]

        button.disabled = True

        self.machine.blank()
        self.machine.log(message)

    def paste_pressed(self):

        url = Clipboard.paste().strip()

        if not url:
            self.machine.blank()
            self.machine.log("Clipboard is empty.")
            return

        self.current_playlist_url = url

        self.machine.major("Custom playlist selected.")
        self.machine.log("Analyzing playlist...")

        self.set_button_state("idle")

        Thread(
            target=self.analyze_playlist_thread,
            daemon=True,
        ).start()

    #

    def analyze_playlist_thread(self):

        result = self.machine.analyze_playlist(
            self.current_playlist_url,
        )

        Clock.schedule_once(
            lambda dt: self.handle_playlist_result(result),
            0,
        )

    def finish_playlist_thread(self):

        success = self.machine.finish_playlist_processing()

        Clock.schedule_once(
            lambda dt: self.finish_playlist_result(success),
            0,
        )

    def sync_csv_thread(self):

        result = self.machine.csv_sync(False, True,)

        Clock.schedule_once(
            lambda dt: self.handle_sync_csv_result(result),
            0,
        )

    def handle_playlist_result(self, result):

        status = result["status"]

        if status == "missing_videos":

            self.machine.major("Fix the playlist on YouTube.")
            self.machine.log("Press Continue when ready.")

            self.pending_action = "retry_playlist"

            self.set_button_state("continue")

        elif status == "csv_ready":

            self.machine.major("Edit the master CSV.")
            self.machine.log("Press Continue when finished.")

            self.pending_action = "csv_finish"

            self.set_button_state("continue")

        elif status == "up_to_date":
            self.machine.blank()
            self.machine.log("Playlist already synchronized.")

            self.set_button_state("idle")

        else:

            self.machine.log("Analysis failed.")

            self.set_button_state("idle")

    def finish_playlist_result(self, success):

        if success:

            self.machine.report("Playlist synchronization complete.")

            self.set_button_state("idle")

        else:

            self.machine.report("CSV validation failed.")
            self.machine.log("Correct the CSV and press Continue.")

            self.pending_action = "csv_finish"

            self.set_button_state("continue")

    def handle_sync_csv_result(self, result):

        if result and result.get("status") == "needs_download":

            self.machine.blank()
            self.machine.log("Undownloaded songs detected.")
            self.machine.blank()
            self.machine.log("Download before synchronizing? (Y/N)")
            self.machine.blank()

            self.pending_action = "sync_download"

            self.set_button_state("yesno")


if __name__ == "__main__":
    LibraryMachineApp().run()
