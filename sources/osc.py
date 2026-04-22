"""
Option 1 — OSC data source.

Listens for broadcasts from Mixxx's built-in OSC client.

Enable in Mixxx:
  Preferences → Controllers → tick "OSC" or find the OSC section
  Set broadcast host = 127.0.0.1, port = 57120 (matches --port default)

Run with --debug to print every OSC message received; useful for
discovering the exact path names your Mixxx version sends.

Known path formats (varies by Mixxx version):
  /mixxx/deck1/playing   /mixxx/deck/playing
  /mixxx/deck1/volume    /mixxx/deck/volume
  /mixxx/deck1/pos       /mixxx/deck/pos
  /mixxx/deck1/bpm       /mixxx/deck/bpm
  /mixxx/deck1/duration  /mixxx/deck/duration
  /mixxx/deck1/title     /mixxx/deck/title

Migration to Option 2 (ControlProxy):
  Implement sources/base.DataSource using Mixxx's C++ ControlProxy
  bindings (e.g. via pybind11 or ctypes).  The interface is identical:
  start(state) populates the same MusicState fields, so the renderer
  requires zero changes.
"""

import logging
import re
import threading

from pythonosc import dispatcher, osc_server

from sources.base import DataSource
from state import MusicState

log = logging.getLogger(__name__)

# Regex to extract deck number from a path segment like "deck1", "deck2", "deck"
_DECK_RE = re.compile(r"deck(\d+)?")


def _deck_num(path: str) -> int:
    m = _DECK_RE.search(path)
    if m and m.group(1):
        return int(m.group(1))
    return 1  # default


class OscDataSource(DataSource):
    def __init__(self, host: str = "0.0.0.0", port: int = 57120, debug: bool = False):
        self._host = host
        self._port = port
        self._debug = debug
        self._server = None
        self._thread = None
        self._state: MusicState | None = None

    # ------------------------------------------------------------------ #
    #  Lifecycle                                                           #
    # ------------------------------------------------------------------ #

    def start(self, state: MusicState) -> None:
        self._state = state
        d = dispatcher.Dispatcher()

        # Register handlers for both /mixxx/deck1/... and /mixxx/deck/... formats
        for prefix in ("/mixxx/deck1", "/mixxx/deck2", "/mixxx/deck"):
            d.map(f"{prefix}/playing",  self._on_playing)
            d.map(f"{prefix}/volume",   self._on_volume)
            d.map(f"{prefix}/pos",      self._on_position)
            d.map(f"{prefix}/duration", self._on_duration)
            d.map(f"{prefix}/title",    self._on_title)
            d.map(f"{prefix}/bpm",      self._on_bpm)

        d.map("/mixxx/master/volume",     self._on_master_volume)
        d.map("/mixxx/master/crossfader", self._on_crossfader)

        # Catch-all: logs unknown paths in debug mode and tries to parse them
        d.set_default_handler(self._on_unknown)

        self._server = osc_server.ThreadingOSCUDPServer((self._host, self._port), d)
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True, name="osc-listener"
        )
        self._thread.start()
        log.info("OSC listening on %s:%d", self._host, self._port)

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()

    # ------------------------------------------------------------------ #
    #  Handlers                                                            #
    # ------------------------------------------------------------------ #

    def _deck(self, path: str):
        n = _deck_num(path)
        return (self._state.deck1 if n == 1 else self._state.deck2), n

    def _on_playing(self, path, *args):
        deck, _ = self._deck(path)
        deck.playing = bool(int(args[0])) if args else False

    def _on_volume(self, path, *args):
        deck, _ = self._deck(path)
        deck.volume = float(args[0]) if args else 0.0

    def _on_position(self, path, *args):
        if not args:
            return
        _, n = self._deck(path)
        self._state.update_position(n, float(args[0]))

    def _on_duration(self, path, *args):
        deck, _ = self._deck(path)
        deck.duration = float(args[0]) if args else 0.0

    def _on_title(self, path, *args):
        deck, _ = self._deck(path)
        deck.title = str(args[0]) if args else "---"

    def _on_bpm(self, path, *args):
        deck, _ = self._deck(path)
        deck.bpm = float(args[0]) if args else 0.0

    def _on_master_volume(self, path, *args):
        if args:
            self._state.master_volume = float(args[0])

    def _on_crossfader(self, path, *args):
        if args:
            self._state.crossfader = float(args[0])

    def _on_unknown(self, path, *args):
        if self._debug:
            print(f"[OSC] {path}  {args}")
