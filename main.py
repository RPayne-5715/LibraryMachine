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

from kivy.graphics import StencilPush, StencilUse, StencilUnUse, StencilPop

import sys
from pathlib import Path
from datetime import datetime
from threading import Thread

sys.path.insert(0, str(Path(__file__).parent / "vendor"))

import yt_dlp
from urllib.parse import urlparse, parse_qs
import csv
import re
from mutagen.oggopus import OggOpus
from pytubefix import Playlist


class TestApp(App):
    def build(self):
        playlist = Playlist(
            "https://www.youtube.com/playlist?list=PL123456789"
        )
        return Label(text=f"{playlist} imported")


TestApp().run()
