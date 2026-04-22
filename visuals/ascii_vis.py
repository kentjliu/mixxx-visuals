"""
ASCII art visualiser driven by MusicState.

Effect: concentric ripple rings that expand outward from the center on
every beat.  Ring sharpness, speed and brightness all track live BPM
and volume.  A second harmonic ring fires on half-beats for density.

Controls (while running):
  q / ESC  — quit
  m        — cycle visual mode (ripple → bars → combined)
  +/-      — increase / decrease visual intensity
"""

import curses
import math
import time

from state import MusicState

TARGET_FPS = 30

# Character density ramp: space = dark, @ = bright
_CHARS = " .,:;!|*#@"

# Colour-pair assignments (1-indexed, 0 is reserved by curses)
_PALETTE = [
    curses.COLOR_BLUE,
    curses.COLOR_CYAN,
    curses.COLOR_GREEN,
    curses.COLOR_YELLOW,
    curses.COLOR_RED,
    curses.COLOR_MAGENTA,
    curses.COLOR_WHITE,
]


def _setup_colors() -> int:
    curses.start_color()
    try:
        curses.use_default_colors()
        bg = -1
    except Exception:
        bg = curses.COLOR_BLACK

    for i, fg in enumerate(_PALETTE, start=1):
        curses.init_pair(i, fg, bg)

    return len(_PALETTE)


class AsciiVisualizer:
    def __init__(self, win, state: MusicState):
        self.win = win
        self.state = state
        self.num_colors = _setup_colors()
        self._mode = 0          # 0=ripple, 1=bars, 2=combined
        self._intensity = 1.0   # user-adjustable gain

        curses.curs_set(0)
        self.win.nodelay(True)

    # ------------------------------------------------------------------ #
    #  Main loop                                                           #
    # ------------------------------------------------------------------ #

    def run(self) -> None:
        frame_dt = 1.0 / TARGET_FPS
        while True:
            t = time.time()

            key = self.win.getch()
            if key in (ord("q"), 27):       # q or ESC
                break
            elif key == ord("m"):
                self._mode = (self._mode + 1) % 3
            elif key in (ord("+"), ord("=")):
                self._intensity = min(2.0, self._intensity + 0.1)
            elif key == ord("-"):
                self._intensity = max(0.1, self._intensity - 0.1)

            self.win.erase()
            self._draw(t)
            self.win.refresh()

            sleep = frame_dt - (time.time() - t)
            if sleep > 0:
                time.sleep(sleep)

    # ------------------------------------------------------------------ #
    #  Top-level draw                                                      #
    # ------------------------------------------------------------------ #

    def _draw(self, t: float) -> None:
        h, w = self.win.getmaxyx()
        if h < 6 or w < 20:
            return

        state = self.state
        deck = state.active_deck()
        beat_phase = state.beat_phase()
        volume = max(deck.volume, 0.04) * self._intensity
        bpm = deck.bpm if deck.bpm > 0 else 120.0

        vis_h = h - 3  # reserve bottom rows for info bar

        if self._mode == 0:
            self._draw_ripple(vis_h, w, beat_phase, volume)
        elif self._mode == 1:
            self._draw_bars(vis_h, w, beat_phase, volume)
        else:
            self._draw_ripple(vis_h, w, beat_phase, volume * 0.7)
            self._draw_bars_overlay(vis_h, w, beat_phase, volume)

        self._draw_info(h, w, deck, beat_phase, bpm)

    # ------------------------------------------------------------------ #
    #  Visual mode: ripple rings                                           #
    # ------------------------------------------------------------------ #

    def _draw_ripple(self, h: int, w: int, beat_phase: float, volume: float) -> None:
        """
        Expanding ring that fires on each beat.

        Math:
          - current ring front is at normalised radius  r = beat_phase
          - for each pixel at normalised distance d from centre,
            intensity = gaussian centred on r=d
          - second harmonic: ring fires again at half-beat
        """
        cx = w / 2.0
        cy = h / 2.0
        # Terminal chars are ~2x taller than wide; correct aspect so rings
        # look round rather than elliptical.
        aspect = 2.2

        for y in range(h):
            for x in range(w):
                dx = (x - cx) / (cx)
                dy = (y - cy) / (cy) * aspect
                d = math.sqrt(dx * dx + dy * dy)  # 0 at centre, ~sqrt(5) at corner
                # Normalise so the ring fills the screen: max d in a rectangle
                # corner = sqrt((aspect)^2 + 1) ≈ 2.4; normalise to ~1 at edge
                d_norm = d / (aspect * 0.9)

                # Main ring at current beat_phase
                diff = d_norm - beat_phase
                intensity = math.exp(-diff * diff * 18.0)

                # Half-beat harmonic
                half_phase = (beat_phase * 2) % 1.0
                diff2 = d_norm - half_phase
                intensity += math.exp(-diff2 * diff2 * 28.0) * 0.45

                # Volume envelope + distance falloff (rings fade as they reach edges)
                falloff = math.exp(-d_norm * 0.9)
                intensity *= volume * falloff
                intensity = max(0.0, min(1.0, intensity))

                char_idx = int(intensity * (len(_CHARS) - 1))
                char = _CHARS[char_idx]

                # Hue: rotates with beat_phase; distance adds a slow colour band
                hue_idx = int((beat_phase * self.num_colors + d_norm * 2) % self.num_colors)
                attr = curses.color_pair(hue_idx + 1)
                if intensity > 0.55:
                    attr |= curses.A_BOLD

                try:
                    self.win.addch(y, x, char, attr)
                except curses.error:
                    pass

    # ------------------------------------------------------------------ #
    #  Visual mode: spectrum bars                                          #
    # ------------------------------------------------------------------ #

    def _draw_bars(self, h: int, w: int, beat_phase: float, volume: float) -> None:
        """
        Vertical bars whose heights pulse with the beat.
        Left/right halves mirror each other for symmetry.
        """
        num_bars = w // 3
        bar_width = w // num_bars

        # Animate bar heights: base height * beat pulse
        beat_pulse = math.exp(-beat_phase * 3.5)
        half_pulse = math.exp(-((beat_phase * 2) % 1.0) * 4.5)

        for b in range(num_bars):
            # Each bar has a slightly different phase offset for a wave look
            phase_offset = abs(b - num_bars / 2) / (num_bars / 2)
            bar_beat = beat_pulse * math.exp(-phase_offset * 1.2)
            bar_half = half_pulse * math.exp(-phase_offset * 1.8) * 0.5
            bar_vol = volume * (bar_beat + bar_half)

            bar_h = int(bar_vol * h * 1.2)
            bar_h = min(bar_h, h)

            hue_idx = (b + int(beat_phase * self.num_colors)) % self.num_colors
            attr = curses.color_pair(hue_idx + 1)
            if bar_vol > 0.6:
                attr |= curses.A_BOLD

            col_start = b * bar_width
            for col in range(col_start, min(col_start + bar_width - 1, w - 1)):
                for row in range(h - bar_h, h):
                    char_idx = int((h - row) / max(bar_h, 1) * (len(_CHARS) - 1))
                    char_idx = max(0, len(_CHARS) - 1 - char_idx)
                    try:
                        self.win.addch(row, col, _CHARS[char_idx], attr)
                    except curses.error:
                        pass

    def _draw_bars_overlay(
        self, h: int, w: int, beat_phase: float, volume: float
    ) -> None:
        """Lighter bar overlay on top of ripple (only draws non-space chars)."""
        num_bars = w // 4
        bar_width = max(w // num_bars, 1)
        beat_pulse = math.exp(-beat_phase * 3.5)
        for b in range(num_bars):
            phase_offset = abs(b - num_bars / 2) / max(num_bars / 2, 1)
            bar_vol = volume * beat_pulse * math.exp(-phase_offset * 1.5)
            bar_h = int(bar_vol * h * 0.8)
            bar_h = min(bar_h, h)
            hue_idx = (b * 2 + int(beat_phase * self.num_colors)) % self.num_colors
            attr = curses.color_pair(hue_idx + 1) | curses.A_BOLD
            col = b * bar_width + bar_width // 2
            if col >= w:
                continue
            for row in range(h - bar_h, h):
                try:
                    self.win.addch(row, col, "|", attr)
                except curses.error:
                    pass

    # ------------------------------------------------------------------ #
    #  Info bar                                                            #
    # ------------------------------------------------------------------ #

    def _draw_info(
        self, h: int, w: int, deck, beat_phase: float, bpm: float
    ) -> None:
        bpm_str = f"{bpm:.1f} BPM" if deck.bpm > 0 else "--- BPM"
        status = "▶" if deck.playing else "■"
        mode_str = ["ripple", "bars", "mixed"][self._mode]

        # Position timestamp
        pos_str = ""
        if deck.duration > 0 and deck.position > 0:
            elapsed_s = int(deck.position * deck.duration)
            total_s = int(deck.duration)
            pos_str = f"  {elapsed_s // 60}:{elapsed_s % 60:02d}/{total_s // 60}:{total_s % 60:02d}"

        title = deck.title
        max_title = w - len(bpm_str) - len(pos_str) - 12
        if len(title) > max_title:
            title = title[:max_title - 1] + "…"

        divider = "─" * (w - 1)
        info_line = f" {status} {title}  {bpm_str}{pos_str}  [{mode_str}]"
        info_line = info_line[: w - 1]

        # Flash white on beat, dim cyan otherwise
        on_beat = beat_phase < 0.08 or beat_phase > 0.92
        info_attr = (
            curses.color_pair(7) | curses.A_BOLD
            if on_beat
            else curses.color_pair(2)
        )

        try:
            self.win.addstr(h - 3, 0, divider, curses.color_pair(1))
            self.win.addstr(h - 2, 0, info_line.ljust(w - 1), info_attr)
            hint = " q=quit  m=mode  +/-=brightness"[: w - 1]
            self.win.addstr(h - 1, 0, hint, curses.color_pair(1))
        except curses.error:
            pass
