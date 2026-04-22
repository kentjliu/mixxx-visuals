"""
Shared music state updated by a DataSource and read by the renderer.

Beat phase is interpolated between OSC updates so the visual stays
smooth at 30 fps even though Mixxx only broadcasts every ~500 ms.
"""

import time
from threading import Lock


class DeckState:
    def __init__(self):
        self.playing: bool = False
        self.volume: float = 0.0
        self.position: float = 0.0   # 0.0–1.0 normalised
        self.duration: float = 0.0   # seconds
        self.title: str = "---"
        self.bpm: float = 0.0


class MusicState:
    def __init__(self):
        self.deck1 = DeckState()
        self.deck2 = DeckState()
        self.master_volume: float = 1.0
        self.crossfader: float = 0.5
        self._lock = Lock()
        # Reference point for beat interpolation
        self._ref_time: float = time.time()
        self._ref_pos_seconds: float = 0.0
        # Beat counter — incremented by DataSource on every detected beat;
        # renderer detects new beats by comparing against its local copy.
        self.beat_count: int = 0

    def active_deck(self) -> DeckState:
        """Return the deck that is playing with known BPM, preferring deck 1."""
        if self.deck1.playing and self.deck1.bpm > 0:
            return self.deck1
        if self.deck2.playing and self.deck2.bpm > 0:
            return self.deck2
        if self.deck1.playing:
            return self.deck1
        return self.deck1

    def beat_phase(self) -> float:
        """
        Beat phase in [0.0, 1.0).

        0.0  = beat just fired
        ~1.0 = next beat imminent

        Interpolated using wall-clock time between OSC updates so the
        renderer never stalls waiting for the next 500 ms broadcast.

        Migration note: when switching to ControlProxy (Option 2) this
        method stays identical — only update_position() changes its
        caller.
        """
        deck = self.active_deck()
        if deck.bpm <= 0:
            # Fallback: pulse at 60 BPM from wall clock
            return time.time() % 1.0

        elapsed = time.time() - self._ref_time
        pos_s = self._ref_pos_seconds + elapsed
        beat_duration = 60.0 / deck.bpm
        return (pos_s % beat_duration) / beat_duration

    def update_position(self, deck_num: int, position: float) -> None:
        """Re-anchor the interpolation reference when OSC delivers fresh position."""
        with self._lock:
            deck = self.deck1 if deck_num == 1 else self.deck2
            deck.position = position
            if deck.duration > 0:
                self._ref_pos_seconds = position * deck.duration
                self._ref_time = time.time()
