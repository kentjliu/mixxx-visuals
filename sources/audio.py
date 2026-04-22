"""
Option 1 — Audio capture data source.

Captures audio from any sounddevice input and runs real-time beat
detection (sources/beat_detector.py — pure numpy, no aubio required).

No Mixxx configuration needed: just route its output to a loopback device.

macOS setup:
  1. Install BlackHole: https://existential.audio/blackhole/
  2. Audio MIDI Setup → New Multi-Output Device
       members: your speakers + BlackHole 2ch
  3. Mixxx → Preferences → Sound Hardware → Master output → Multi-Output
  4. python main.py --device "BlackHole 2ch"

Quick smoke test (no loopback):
  python main.py        # captures default mic; play music near it

Migration to Option 2 (ControlProxy):
  Replace this file with sources/control_proxy.py implementing the same
  DataSource interface.  state.py and the renderer are untouched.
"""

import logging
import time

import numpy as np
import sounddevice as sd

from sources.base import DataSource
from sources.beat_detector import BeatDetector
from state import MusicState

log = logging.getLogger(__name__)

SAMPLE_RATE = 44100
HOP_SIZE    = 512   # ~11 ms per callback


def list_devices() -> None:
    print("\nAvailable audio input devices:")
    print("─" * 50)
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0:
            marker = "  ◀ default" if i == sd.default.device[0] else ""
            print(f"  [{i:2d}]  {dev['name']}{marker}")
    print()


class AudioDataSource(DataSource):
    def __init__(self, device=None):
        self._device  = device
        self._state: MusicState | None = None
        self._stream  = None
        self._detector: BeatDetector | None = None

    def start(self, state: MusicState) -> None:
        self._state    = state
        self._detector = BeatDetector(sample_rate=SAMPLE_RATE, hop_size=HOP_SIZE)

        self._stream = sd.InputStream(
            device=self._device,
            channels=1,
            samplerate=SAMPLE_RATE,
            blocksize=HOP_SIZE,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()
        state.deck1.playing = True
        log.info("Audio stream started (device=%s)", self._device or "default")

    def stop(self) -> None:
        if self._stream:
            self._stream.stop()
            self._stream.close()
        if self._state:
            self._state.deck1.playing = False

    def _callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        if status:
            log.debug("sounddevice: %s", status)

        samples = indata[:, 0]

        # Volume: scaled RMS so typical music sits around 0.3–0.8
        rms = float(np.sqrt(np.mean(samples ** 2)))
        self._state.deck1.volume = min(rms * 8.0, 1.0)

        is_beat, bpm = self._detector.process(samples)

        if bpm > 0:
            self._state.deck1.bpm = bpm

        self._state.bass = self._detector.bass
        self._state.mid  = self._detector.mid
        self._state.high = self._detector.high

        if is_beat:
            self._state._ref_time = time.time()
            self._state._ref_pos_seconds = 0.0
            self._state.beat_count += 1
