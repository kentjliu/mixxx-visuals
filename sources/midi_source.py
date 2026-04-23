"""
Mixxx ControlProxy data source — reads BPM, beat phase, play state, and
volume from the Mixxx Visuals Bridge controller script via MIDI SysEx.

Setup:
  macOS:
    1. Audio MIDI Setup → Window → Show MIDI Studio
    2. Double-click IAC Driver → check "Device is online"
    3. Copy controller/*.xml and controller/*.js to Mixxx's controllers dir:
         ~/Library/Containers/org.mixxx.mixxx/Data/Library/
           Application Support/Mixxx/controllers/
    4. Mixxx → Preferences → Controllers → enable "Mixxx Visuals Bridge"
       and set its OUTPUT port to "IAC Driver Bus 1"
    5. python main.py --window --mixxx

  Linux:
    Use a virtual MIDI port (e.g. ALSA's "Virtual Raw MIDI") and adjust
    --midi-port to match.

SysEx format (10 bytes):
  F0 7D 01 <deck> <bpm_msb> <bpm_lsb> <beat> <vol> <play> F7
  bpm  = ((bpm_msb << 7) | bpm_lsb) / 10.0
  beat = beat_byte / 127.0   (0 = just fired, 1 = next imminent)
  vol  = vol_byte  / 127.0
"""

import logging
import time

import rtmidi

from sources.base import DataSource
from state import MusicState

log = logging.getLogger(__name__)

_SYSEX_HEADER = (0xF0, 0x7D, 0x01)
_MSG_LEN      = 10


def list_midi_ports() -> None:
    midi_in = rtmidi.MidiIn()
    ports   = midi_in.get_ports()
    print("\nAvailable MIDI input ports:")
    print("─" * 50)
    for i, name in enumerate(ports):
        print(f"  [{i:2d}]  {name}")
    print()
    del midi_in


class MixxxMidiSource(DataSource):
    """Receive Mixxx state via the SysEx MIDI bridge."""

    def __init__(self, port: str | int = "IAC Driver Bus 1"):
        self._port    = port
        self._midi_in = None
        self._state: MusicState | None = None
        self._last_beat_dist = [0.0, 0.0]   # per deck; used to detect crossings

    # ── DataSource interface ────────────────────────────────────────────────

    def start(self, state: MusicState) -> None:
        self._state = state
        self._midi_in = rtmidi.MidiIn()
        self._midi_in.ignore_types(sysex=False, timing=True, active_sense=True)

        port_idx = self._resolve_port()
        self._midi_in.open_port(port_idx)
        self._midi_in.set_callback(self._on_midi)

        log.info("MIDI source started (port=%s)", self._midi_in.get_port_name(port_idx))

    def stop(self) -> None:
        if self._midi_in:
            self._midi_in.close_port()
            del self._midi_in
            self._midi_in = None

    # ── Internal ────────────────────────────────────────────────────────────

    def _resolve_port(self) -> int:
        ports = self._midi_in.get_ports()
        if not ports:
            raise RuntimeError("No MIDI input ports found. Is the IAC Driver enabled?")

        if isinstance(self._port, int):
            return self._port

        needle = self._port.lower()
        for i, name in enumerate(ports):
            if needle in name.lower():
                return i

        raise RuntimeError(
            f"MIDI port '{self._port}' not found.\n"
            f"Available ports: {ports}\n"
            f"Run  python main.py --list-midi  to see them."
        )

    def _on_midi(self, event, _data) -> None:
        msg, _delta = event
        if len(msg) != _MSG_LEN:
            return
        if tuple(msg[:3]) != _SYSEX_HEADER:
            return

        deck_idx  = msg[3]
        bpm_msb   = msg[4]
        bpm_lsb   = msg[5]
        beat_byte = msg[6]
        vol_byte  = msg[7]
        play_byte = msg[8]

        bpm       = ((bpm_msb << 7) | bpm_lsb) / 10.0
        beat_dist = beat_byte / 127.0
        volume    = vol_byte  / 127.0
        playing   = bool(play_byte)

        deck = self._state.deck1 if deck_idx == 0 else self._state.deck2
        deck.bpm     = bpm
        deck.volume  = volume
        deck.playing = playing

        # Detect beat crossing: beat_distance wraps from ~1 → ~0
        prev = self._last_beat_dist[deck_idx]
        if prev > 0.80 and beat_dist < 0.20:
            self._state._ref_time          = time.time()
            self._state._ref_pos_seconds   = 0.0
            self._state.beat_count        += 1
            log.debug("beat detected (deck %d, bpm=%.1f)", deck_idx, bpm)
        self._last_beat_dist[deck_idx] = beat_dist
