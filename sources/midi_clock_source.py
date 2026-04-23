"""
MIDI Clock data source — works with rekordbox, Traktor, Serato, or any
DJ software that sends standard MIDI clock output.

MIDI clock sends 24 pulses per beat (0xF8).  We use the pulse intervals
to compute a smoothed BPM and the pulse count mod 24 to drive beat phase.

rekordbox setup:
  1. Audio MIDI Setup → Window → Show MIDI Studio
     → IAC Driver → check "Device is online"
  2. rekordbox → Preferences → MIDI → Controller:
     - Enable MIDI Clock  (checkbox or toggle)
     - Output: IAC Driver Bus 1
  3. python main.py --window --midi-clock

Combine with audio loopback for frequency-band shader data:
  python main.py --window --midi-clock --device "BlackHole 2ch"
"""

import logging
import time
from collections import deque

import rtmidi

from sources.base import DataSource
from state import MusicState

log = logging.getLogger(__name__)

_CLOCKS_PER_BEAT = 24

# MIDI realtime status bytes
_CLOCK = 0xF8
_START = 0xFA
_CONT  = 0xFB
_STOP  = 0xFC


class MidiClockSource(DataSource):
    """Derive BPM and beat phase from MIDI clock pulses."""

    def __init__(self, port: str | int = "IAC Driver Bus 1"):
        self._port     = port
        self._midi_in  = None
        self._state: MusicState | None = None

        self._pulse_count    = 0
        self._last_clock_t   = None
        # Rolling window of inter-pulse intervals → smooth BPM estimate
        self._intervals: deque[float] = deque(maxlen=_CLOCKS_PER_BEAT * 2)

    # ── DataSource interface ────────────────────────────────────────────────

    def start(self, state: MusicState) -> None:
        self._state = state
        self._midi_in = rtmidi.MidiIn()
        # Must NOT ignore timing messages — that's what clock is
        self._midi_in.ignore_types(sysex=True, timing=False, active_sense=True)

        port_idx = self._resolve_port()
        self._midi_in.open_port(port_idx)
        self._midi_in.set_callback(self._on_midi)
        log.info("MIDI clock source started (port=%s)",
                 self._midi_in.get_port_name(port_idx))

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
            f"Available: {ports}\n"
            f"Run  python main.py --list-midi  to see all ports."
        )

    def _on_midi(self, event, _data) -> None:
        msg, _delta = event
        if not msg:
            return
        status = msg[0] & 0xFF

        if status == _CLOCK:
            self._on_clock()
        elif status == _START:
            self._pulse_count = 0
            self._last_clock_t = None
            self._intervals.clear()
            self._state.deck1.playing = True
            log.debug("MIDI Start")
        elif status == _CONT:
            self._state.deck1.playing = True
            log.debug("MIDI Continue")
        elif status == _STOP:
            self._state.deck1.playing = False
            log.debug("MIDI Stop")

    def _on_clock(self) -> None:
        now = time.time()

        if self._last_clock_t is not None:
            interval = now - self._last_clock_t
            # Sanity-check: ignore jitter spikes (< 20 BPM or > 300 BPM)
            if 1.0 / (interval * _CLOCKS_PER_BEAT) > 20:
                self._intervals.append(interval)

            if len(self._intervals) >= 4:
                avg_interval = sum(self._intervals) / len(self._intervals)
                bpm = 60.0 / (avg_interval * _CLOCKS_PER_BEAT)
                self._state.deck1.bpm = round(bpm, 1)

        self._last_clock_t = now
        self._pulse_count += 1

        # Every 24 pulses = one beat
        if self._pulse_count % _CLOCKS_PER_BEAT == 0:
            self._state._ref_time        = now
            self._state._ref_pos_seconds = 0.0
            self._state.beat_count      += 1
            log.debug("beat  bpm=%.1f", self._state.deck1.bpm)
