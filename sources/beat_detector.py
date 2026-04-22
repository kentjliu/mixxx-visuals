"""
Lightweight real-time beat detector — pure numpy, no aubio needed.

Algorithm:
  1. Buffer incoming audio into overlapping 2048-sample windows for better
     FFT frequency resolution (~21 Hz bins at 44100 Hz).
  2. Isolate the bass band (40–200 Hz) where kick drums live.
  3. Compare current bass energy against a short local average.
     A beat fires when energy spikes well above the recent baseline,
     subject to a minimum inter-beat gap (max 240 BPM).
  4. BPM is estimated from a median of the last several inter-beat intervals.
"""

import time
import numpy as np

_FFT_SIZE    = 2048
_HISTORY_LEN = 60     # buffers of local energy history (~700 ms at 512-hop)
_THRESHOLD_C = 1.4    # spike must exceed mean + C*std
_MIN_MULT    = 1.25   # spike must also be >= 125% of mean (silence guard)
_MIN_GAP     = 0.25   # seconds — prevents double-triggers (max 240 BPM)
_MAX_GAP     = 1.6    # seconds — above this we don't use the interval for BPM
_BPM_WINDOW  = 10.0   # seconds of beat history used for BPM median


class BeatDetector:
    def __init__(self, sample_rate: int = 44100, hop_size: int = 512):
        self.sample_rate = sample_rate
        self.hop_size    = hop_size
        self.bpm: float  = 0.0

        # Overlapping FFT window
        self._window  = np.zeros(_FFT_SIZE, dtype=np.float32)
        # Frequency bins for the bass band
        freqs         = np.fft.rfftfreq(_FFT_SIZE, 1.0 / sample_rate)
        self._bass    = (freqs >= 40) & (freqs <= 200)
        # Hann window to reduce spectral leakage
        self._hann    = np.hanning(_FFT_SIZE).astype(np.float32)

        # Rolling energy history
        self._history     = np.zeros(_HISTORY_LEN, dtype=np.float32)
        self._history_ptr = 0
        self._filled      = 0

        # Beat timing
        self._last_beat: float = 0.0
        self._beat_times: list[float] = []

    # ------------------------------------------------------------------ #

    def process(self, samples: np.ndarray) -> tuple[bool, float]:
        """
        Feed one audio hop.  Returns (is_beat, current_bpm).
        samples must have length == hop_size.
        """
        # Shift window and insert new hop
        self._window = np.roll(self._window, -self.hop_size)
        self._window[-self.hop_size:] = samples

        # Bass energy via FFT
        spectrum = np.fft.rfft(self._window * self._hann)
        bass_energy = float(np.mean(np.abs(spectrum[self._bass]) ** 2)) ** 0.5

        # Update history ring buffer
        self._history[self._history_ptr] = bass_energy
        self._history_ptr = (self._history_ptr + 1) % _HISTORY_LEN
        self._filled = min(self._filled + 1, _HISTORY_LEN)

        # Need at least half the history before detecting
        if self._filled < _HISTORY_LEN // 2:
            return False, 0.0

        hist = self._history[: self._filled]
        mean = float(np.mean(hist))
        std  = float(np.std(hist))
        threshold = mean + _THRESHOLD_C * std

        now            = time.time()
        since_last     = now - self._last_beat
        is_silence     = mean < 1e-5

        is_beat = (
            not is_silence
            and bass_energy > threshold
            and bass_energy >= mean * _MIN_MULT
            and since_last >= _MIN_GAP
        )

        if is_beat:
            if 0 < since_last <= _MAX_GAP and self._last_beat > 0:
                self._beat_times.append(now)
                cutoff = now - _BPM_WINDOW
                self._beat_times = [t for t in self._beat_times if t > cutoff]
                if len(self._beat_times) >= 4:
                    intervals = np.diff(self._beat_times[-16:])  # last 16 gaps
                    median_iv = float(np.median(intervals))
                    if _MIN_GAP < median_iv < _MAX_GAP:
                        self.bpm = round(60.0 / median_iv, 1)
            self._last_beat = now

        return is_beat, self.bpm
