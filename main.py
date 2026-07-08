from kivy.app import App
from kivy.lang import Builder
from kivy.core.window import Window
from kivy.core.text import LabelBase
from kivy.core.image import Image as CoreImage
from kivy.properties import NumericProperty
from kivy.uix.widget import Widget
from kivy.uix.label import Label
from kivy.uix.screenmanager import ScreenManager, FadeTransition, Screen
from kivy.animation import Animation
from kivy.clock import Clock
from kivy.properties import NumericProperty, StringProperty, BooleanProperty
from kivy.utils import platform

from pathlib import Path
from datetime import datetime
from threading import Thread

from backend import LibraryMachine, PLAYLIST_URLS

gradient = CoreImage("assets/progress_gradient.png").texture
gradient.wrap = "clamp_to_edge"
gradient.mag_filter = "linear"
gradient.min_filter = "linear"
current_label = None
CONSOLE_PADDING = 20

Window.clearcolor = (
    0x1C / 255,
    0x1C / 255,
    0x1C / 255,
    1,
)

if platform != "android":
    Window.size = (412, 915)

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
    hr = "==========================="

    def build(self):
        self.machine = None

        self.pending_action = None
        self.current_playlist_url = None

        return None

    def on_start(self):
        self.machine = LibraryMachine(
            library_path=Path(App.get_running_app().user_data_dir) / "PlaylistLibrary",
            log_callback=log,
            progress_callback=self.update_progress,
        )

        Clock.schedule_once(
            self.finish_loading,
            3,
        )

    def on_pause(self):
        return True

    def on_resume(self):
        pass

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
            self. machine.log("")

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

        log("")
        log(f"Saved log to {filename}")

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
                target=lambda: self.machine.csv_sync(True),
                daemon=True,
            ).start()

            self.pending_action = None

    def no_pressed(self):

        if self.pending_action == "sync_download":

            self.set_button_state("idle")

            Thread(
                target=lambda: self.machine.csv_sync(False),
                daemon=True,
            ).start()

            self.pending_action = None

    def continue_pressed(self):

        if self.pending_action == "retry_playlist":

            log("")
            log("Analyzing playlist...")

            self.set_button_state("idle")

            Thread(
                target=self.analyze_playlist_thread,
                daemon=True,
            ).start()

        elif self.pending_action == "csv_finish":

            log("")
            log("Downloading songs...")

            self.set_button_state("idle")

            Thread(
                target=self.finish_playlist_thread,
                daemon=True,
            ).start()

        self.pending_action = None

    #

    def folder_pressed(self):
        log("Not Yet Implemented")

    def player_pressed(self):
        log("Not Yet Implemented")

    def csv_pressed(self):
        log("Not Yet Implemented")  

    def sync_csv_pressed(self):
        if self.machine.needs_download_before_sync():

            log("")
            log("Undownloaded songs detected.")
            log("Download before synchronizing? (Y/N)")

            self.pending_action = "sync_download"
            self.set_button_state("yesno")

        else:

            self.set_button_state("idle")

            Thread(
                target=lambda: self.machine.csv_sync(False),
                daemon=True,
            ).start()

    def sync_yt_pressed(self):
        log("Not Yet Implemented")

    def playlist_pressed(self, playlist):

        if playlist == 5:

            log(self.hr)
            log("Paste yout custom YouTube URL.")

            self.current_playlist_url = None
            self.set_button_state("paste")
            return

        self.current_playlist_url = PLAYLIST_URLS[playlist]

        names = {
            1: "Dollop",
            2: "Peer",
            3: "PeerJ",
            4: "For Dakota ig",
        }

        log(self.hr)
        log("")
        log(f"{names[playlist]} selected.")
        log("")
        log("Analyzing playlist...")

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

    def handle_playlist_result(self, result):

        status = result["status"]

        if status == "missing_videos":

            log("")
            log("Fix the playlist on YouTube.")
            log("Press Continue when ready.")

            self.pending_action = "retry_playlist"

            self.set_button_state("continue")

        elif status == "csv_ready":

            log("")
            log("Edit the master CSV.")
            log("Press Continue when finished.")

            self.pending_action = "csv_finish"

            self.set_button_state("continue")

        elif status == "up_to_date":

            log("")
            log("Playlist already synchronized.")
            log("")

            self.set_button_state("idle")

        else:

            log("")
            log("Analysis failed.")

            self.set_button_state("idle")

    def finish_playlist_thread(self):

        success = self.machine.finish_playlist_processing()

        Clock.schedule_once(
            lambda dt: self.finish_playlist_result(success),
            0,
        )

    def finish_playlist_result(self, success):

        if success:

            log("")
            log("Playlist synchronization complete.")

            self.set_button_state("idle")

        else:

            log("")
            log("CSV validation failed.")
            log("Correct the CSV and press Continue.")

            self.pending_action = "csv_finish"

            self.set_button_state("continue")

if __name__ == "__main__":
    LibraryMachineApp().run()
