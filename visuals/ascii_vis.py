"""
ASCII art visualiser — 6 modes, all driven by MusicState.

Keys:
  m      — cycle mode
  +/-    — brightness
  q/ESC  — quit

Modes (in order):
  ripple    concentric rings expanding on every beat
  plasma    demoscene sine-wave plasma, hue drifts with BPM
  matrix    Matrix-style falling character rain
  fire      ASCII fire that surges on beat
  particles burst of sparks from centre on every beat
  dancer    stick figure cycling through dance poses each beat
"""

import curses
import math
import random
import time
from dataclasses import dataclass, field

import numpy as np

from state import MusicState

TARGET_FPS = 30

# --------------------------------------------------------------------------- #
#  Character palettes                                                           #
# --------------------------------------------------------------------------- #

_DENSITY  = " .,:;!|*#@"        # darkness ramp for ripple / plasma
_FIRE_CH  = " .,:;+=xX$&#"      # brightness ramp for fire
_MATRIX_CH = (
    "ｦｧｨｩｪｫｬｭｮｯｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝ"
    "0123456789@#$%&"
)
_SPARK_CH = "*+.oO@#x~"

# --------------------------------------------------------------------------- #
#  Colour palette (7 pairs, 1-indexed)                                         #
# --------------------------------------------------------------------------- #

_PALETTE = [
    curses.COLOR_BLUE,
    curses.COLOR_CYAN,
    curses.COLOR_GREEN,
    curses.COLOR_YELLOW,
    curses.COLOR_RED,
    curses.COLOR_MAGENTA,
    curses.COLOR_WHITE,
]
# Logical indices for readability
_BLUE, _CYAN, _GREEN, _YELLOW, _RED, _MAGENTA, _WHITE = range(1, 8)


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


# --------------------------------------------------------------------------- #
#  Dancer poses                                                                #
# --------------------------------------------------------------------------- #
# Each pose: list of strings, 6 rows × 11 chars (will be centred on screen).

DANCER_POSES = [
    # 0: BEAT — big arms-up move
    [r"   \\ O //  ",
     r"    \\|//   ",
     r"     |      ",
     r"   --|--    ",
     r"    / \     ",
     r"   /   \    "],
    # 1: neutral groove
    [r"     O      ",
     r"    /|\     ",
     r"     |      ",
     r"     |      ",
     r"    / \     ",
     r"   /   \    "],
    # 2: lean right
    [r"     O      ",
     r"     |\     ",
     r"    /|      ",
     r"     |      ",
     r"    /|\     ",
     r"   /   \    "],
    # 3: crouch
    [r"     O      ",
     r"    \|/     ",
     r"     |      ",
     r"    / \     ",
     r"   /   \    ",
     r"  /     \   "],
    # 4: lean left
    [r"     O      ",
     r"    /|      ",
     r"     |\     ",
     r"     |      ",
     r"    /|\     ",
     r"   /   \    "],
    # 5: jump
    [r"   \oO/     ",
     r"     |      ",
     r"    /|\     ",
     r"     |      ",
     r"    / \     ",
     r"   /   \    "],
    # 6: arms wide
    [r"\   O   /   ",
     r" \  |  /    ",
     r"   \|/      ",
     r"    |       ",
     r"   / \      ",
     r"  /   \     "],
    # 7: step right
    [r"     O      ",
     r"     |\     ",
     r"    /|      ",
     r"   / |      ",
     r"  /  |      ",
     r"      \     "],
]

# --------------------------------------------------------------------------- #
#  Particle                                                                    #
# --------------------------------------------------------------------------- #

@dataclass
class _Particle:
    x: float
    y: float
    vx: float
    vy: float
    char: str
    color: int
    age: int = 0
    max_age: int = 22


# --------------------------------------------------------------------------- #
#  Main visualiser                                                             #
# --------------------------------------------------------------------------- #

class AsciiVisualizer:
    def __init__(self, win, state: MusicState):
        self.win   = win
        self.state = state
        self.num_colors = _setup_colors()
        curses.curs_set(0)
        self.win.nodelay(True)

        self._intensity  = 1.0
        self._mode_idx   = 0
        self._modes      = [
            ("ripple",    self._draw_ripple),
            ("plasma",    self._draw_plasma),
            ("matrix",    self._draw_matrix),
            ("fire",      self._draw_fire),
            ("particles", self._draw_particles),
            ("dancer",    self._draw_dancer),
        ]

        # Beat tracking (renderer-side)
        self._last_beat_count = 0

        # Per-mode persistent state
        self._matrix_heads  = None   # np array, reset on resize
        self._matrix_speeds = None
        self._matrix_lens   = None
        self._fire_buf      = None   # np array, reset on resize
        self._particles: list[_Particle] = []
        self._dancer_frame  = 0

    # ----------------------------------------------------------------------- #
    #  Main loop                                                               #
    # ----------------------------------------------------------------------- #

    def run(self) -> None:
        frame_dt = 1.0 / TARGET_FPS
        while True:
            t = time.time()

            key = self.win.getch()
            if key in (ord("q"), 27):
                break
            elif key == ord("m"):
                self._mode_idx = (self._mode_idx + 1) % len(self._modes)
                # Reset mode-specific buffers so they re-init at correct size
                self._matrix_heads = None
                self._fire_buf = None
            elif key in (ord("+"), ord("=")):
                self._intensity = min(2.0, self._intensity + 0.1)
            elif key == ord("-"):
                self._intensity = max(0.1, self._intensity - 0.1)

            # Detect new beats
            if self.state.beat_count != self._last_beat_count:
                self._on_beat()
                self._last_beat_count = self.state.beat_count

            self.win.erase()
            h, w = self.win.getmaxyx()
            vis_h = max(h - 3, 1)

            name, draw_fn = self._modes[self._mode_idx]
            draw_fn(vis_h, w, t)
            self._draw_info(h, w, name)
            self.win.refresh()

            sleep = frame_dt - (time.time() - t)
            if sleep > 0:
                time.sleep(sleep)

    def _on_beat(self) -> None:
        """Fires once per detected beat — advance beat-synced state."""
        self._dancer_frame = (self._dancer_frame + 1) % len(DANCER_POSES)
        self._spawn_particles()

    # ----------------------------------------------------------------------- #
    #  Mode: ripple                                                            #
    # ----------------------------------------------------------------------- #

    def _draw_ripple(self, h: int, w: int, t: float) -> None:
        state      = self.state
        bp         = state.beat_phase()
        volume     = max(state.deck1.volume, 0.04) * self._intensity
        cx, cy     = w / 2.0, h / 2.0
        aspect     = 2.2

        for y in range(h):
            for x in range(w):
                dx     = (x - cx) / cx
                dy     = (y - cy) / cy * aspect
                d      = math.sqrt(dx * dx + dy * dy) / (aspect * 0.9)
                diff   = d - bp
                i      = math.exp(-diff * diff * 18.0)
                # half-beat harmonic
                hp     = (bp * 2) % 1.0
                diff2  = d - hp
                i     += math.exp(-diff2 * diff2 * 28.0) * 0.45
                i     *= volume * math.exp(-d * 0.9)
                i      = max(0.0, min(1.0, i))

                char = _DENSITY[int(i * (len(_DENSITY) - 1))]
                hue  = int((bp * self.num_colors + d * 2) % self.num_colors)
                attr = curses.color_pair(hue + 1)
                if i > 0.55:
                    attr |= curses.A_BOLD
                try:
                    self.win.addch(y, x, char, attr)
                except curses.error:
                    pass

    # ----------------------------------------------------------------------- #
    #  Mode: plasma                                                            #
    # ----------------------------------------------------------------------- #

    def _draw_plasma(self, h: int, w: int, t: float) -> None:
        state  = self.state
        bp     = state.beat_phase()
        volume = max(state.deck1.volume, 0.05) * self._intensity
        bpm    = state.deck1.bpm or 120.0
        # Time advances proportionally to BPM so the pattern moves with the music
        mt     = t * (bpm / 120.0) * 0.4
        flash  = math.exp(-bp * 4.0) * 0.35

        x  = np.linspace(-3.0, 3.0, w)
        y  = np.linspace(-2.0, 2.0, h)
        X, Y = np.meshgrid(x, y)
        R  = np.sqrt(X ** 2 + Y ** 2)

        Z = (np.sin(X + mt)
             + np.sin(Y + mt * 0.9)
             + np.sin((X + Y) * 0.5 + mt * 0.7)
             + np.sin(R + mt))                    # shape (h, w)

        intensity = np.clip((Z + 4) / 8 * (0.4 + volume) + flash, 0.0, 1.0)
        hue_map   = ((Z * 1.5 + mt * 2) % self.num_colors).astype(int) % self.num_colors

        chars = _DENSITY
        nc    = len(chars)
        for row in range(h):
            for col in range(w):
                iv   = intensity[row, col]
                char = chars[int(iv * (nc - 1))]
                attr = curses.color_pair(int(hue_map[row, col]) + 1)
                if iv > 0.6:
                    attr |= curses.A_BOLD
                try:
                    self.win.addch(row, col, char, attr)
                except curses.error:
                    pass

    # ----------------------------------------------------------------------- #
    #  Mode: matrix rain                                                       #
    # ----------------------------------------------------------------------- #

    def _draw_matrix(self, h: int, w: int, t: float) -> None:
        # (Re)initialise column state when terminal resizes
        if self._matrix_heads is None or len(self._matrix_heads) != w:
            self._matrix_heads  = np.random.uniform(-h, 0, w)
            self._matrix_speeds = np.random.uniform(0.4, 1.2, w)
            self._matrix_lens   = np.random.randint(6, 24, w)
            self._matrix_chars  = [
                [random.choice(_MATRIX_CH) for _ in range(h + 30)]
                for _ in range(w)
            ]

        state  = self.state
        bp     = state.beat_phase()
        bpm    = state.deck1.bpm or 120.0
        volume = max(state.deck1.volume, 0.15) * self._intensity

        # Advance drops proportional to BPM
        speed_mult         = bpm / 60.0 * volume / TARGET_FPS
        self._matrix_heads += self._matrix_speeds * speed_mult * 3.0

        # Wrap drops that exit the screen
        for c in range(w):
            if self._matrix_heads[c] > h + self._matrix_lens[c]:
                self._matrix_heads[c]  = -self._matrix_lens[c]
                self._matrix_speeds[c] = random.uniform(0.4, 1.2)
                self._matrix_lens[c]   = random.randint(6, 24)
                self._matrix_chars[c]  = [
                    random.choice(_MATRIX_CH) for _ in range(h + 30)
                ]

        on_beat = bp < 0.1

        for c in range(w):
            head = int(self._matrix_heads[c])
            ln   = self._matrix_lens[c]
            col_chars = self._matrix_chars[c]

            for r in range(max(0, head - ln), min(h, head + 1)):
                age  = head - r          # 0 = tip (brightest), ln = tail (dim)
                frac = age / max(ln, 1)  # 0.0→1.0

                if age == 0:
                    char = random.choice(_MATRIX_CH)   # tip flickers
                    attr = curses.color_pair(_WHITE) | curses.A_BOLD
                elif frac < 0.25:
                    char = col_chars[r % len(col_chars)]
                    attr = curses.color_pair(_GREEN) | curses.A_BOLD
                elif frac < 0.6:
                    char = col_chars[r % len(col_chars)]
                    attr = curses.color_pair(_GREEN)
                else:
                    char = col_chars[r % len(col_chars)]
                    attr = curses.color_pair(_CYAN)

                if on_beat:
                    attr |= curses.A_BOLD

                try:
                    self.win.addch(r, c, char, attr)
                except curses.error:
                    pass

    # ----------------------------------------------------------------------- #
    #  Mode: fire                                                              #
    # ----------------------------------------------------------------------- #

    def _draw_fire(self, h: int, w: int, t: float) -> None:
        if self._fire_buf is None or self._fire_buf.shape != (h + 2, w):
            self._fire_buf = np.zeros((h + 2, w), dtype=np.float32)

        state  = self.state
        bp     = state.beat_phase()
        volume = max(state.deck1.volume, 0.1) * self._intensity

        # Heat source: surges on beat, simmers otherwise
        heat = volume * (0.6 + 0.4 * math.exp(-bp * 3.0))
        self._fire_buf[h + 1, :] = np.random.uniform(
            max(0.0, heat - 0.15), min(1.0, heat + 0.05), w
        ).astype(np.float32)

        # Spread upward with cooling  (vectorised — fast)
        self._fire_buf[:h, :] = (
            self._fire_buf[1 : h + 1, :]
            + np.roll(self._fire_buf[1 : h + 1, :],  1, axis=1)
            + np.roll(self._fire_buf[1 : h + 1, :], -1, axis=1)
            + self._fire_buf[2 : h + 2, :]
        ) * 0.25 * 0.96   # 0.96 = cooling factor

        buf   = self._fire_buf
        chars = _FIRE_CH
        nc    = len(chars)

        for row in range(h):
            for col in range(w):
                v    = float(buf[row, col])
                char = chars[int(v * (nc - 1))]

                if v < 0.25:
                    attr = curses.color_pair(_RED)
                elif v < 0.55:
                    attr = curses.color_pair(_RED) | curses.A_BOLD
                elif v < 0.80:
                    attr = curses.color_pair(_YELLOW) | curses.A_BOLD
                else:
                    attr = curses.color_pair(_WHITE) | curses.A_BOLD

                try:
                    self.win.addch(row, col, char, attr)
                except curses.error:
                    pass

    # ----------------------------------------------------------------------- #
    #  Mode: particles                                                         #
    # ----------------------------------------------------------------------- #

    def _spawn_particles(self) -> None:
        h, w   = self.win.getmaxyx()
        cx, cy = w // 2, (h - 3) // 2
        vol    = max(self.state.deck1.volume, 0.3) * self._intensity
        n      = int(20 + vol * 40)

        for _ in range(n):
            angle  = random.uniform(0, 2 * math.pi)
            speed  = random.uniform(0.4, 2.2) * (0.5 + vol)
            self._particles.append(_Particle(
                x=float(cx), y=float(cy),
                vx=math.cos(angle) * speed,
                vy=math.sin(angle) * speed * 0.5,  # aspect correction
                char=random.choice(_SPARK_CH),
                color=random.randint(1, self.num_colors),
                max_age=int(14 + random.uniform(0, 14)),
            ))

    def _draw_particles(self, h: int, w: int, t: float) -> None:
        # Ripple as a subtle background
        bp     = self.state.beat_phase()
        volume = max(self.state.deck1.volume, 0.04) * self._intensity * 0.25
        self._draw_ripple_inner(h, w, bp, volume)

        alive: list[_Particle] = []
        for p in self._particles:
            p.x   += p.vx
            p.y   += p.vy
            p.vy  += 0.04   # gravity
            p.age += 1

            if p.age < p.max_age and 0 <= int(p.y) < h and 0 <= int(p.x) < w:
                fade = 1.0 - p.age / p.max_age
                attr = curses.color_pair(p.color)
                if fade > 0.5:
                    attr |= curses.A_BOLD
                try:
                    self.win.addch(int(p.y), int(p.x), p.char, attr)
                except curses.error:
                    pass
                alive.append(p)

        self._particles = alive

    # ----------------------------------------------------------------------- #
    #  Mode: dancer                                                            #
    # ----------------------------------------------------------------------- #

    def _draw_dancer(self, h: int, w: int, t: float) -> None:
        state  = self.state
        bp     = state.beat_phase()
        volume = max(state.deck1.volume, 0.05) * self._intensity

        # Plasma as background at low intensity
        bpm = state.deck1.bpm or 120.0
        mt  = t * (bpm / 120.0) * 0.4
        x   = np.linspace(-3.0, 3.0, w)
        y   = np.linspace(-2.0, 2.0, h)
        X, Y = np.meshgrid(x, y)
        Z   = np.sin(X + mt) + np.sin(Y + mt * 0.9) + np.sin(np.sqrt(X**2+Y**2) + mt)
        intensity_bg = np.clip((Z + 3) / 6 * volume * 0.35, 0.0, 1.0)
        hue_bg = ((Z + mt) % self.num_colors).astype(int) % self.num_colors
        chars  = _DENSITY
        nc     = len(chars)
        for row in range(h):
            for col in range(w):
                iv   = intensity_bg[row, col]
                if iv < 0.05:
                    continue
                char = chars[int(iv * (nc - 1))]
                attr = curses.color_pair(int(hue_bg[row, col]) + 1)
                try:
                    self.win.addch(row, col, char, attr)
                except curses.error:
                    pass

        # Dancer pose
        pose    = DANCER_POSES[self._dancer_frame % len(DANCER_POSES)]
        pose_h  = len(pose)
        pose_w  = max(len(r) for r in pose)
        start_y = h // 2 - pose_h // 2
        start_x = w // 2 - pose_w // 2

        on_beat  = bp < 0.15
        if on_beat:
            figure_attr = curses.color_pair(_WHITE) | curses.A_BOLD
        else:
            hue = int(bp * self.num_colors) % self.num_colors
            figure_attr = curses.color_pair(hue + 1) | curses.A_BOLD

        for ri, row in enumerate(pose):
            py = start_y + ri
            if not (0 <= py < h):
                continue
            for ci, ch in enumerate(row):
                px = start_x + ci
                if 0 <= px < w and ch not in (" ", "\t"):
                    try:
                        self.win.addch(py, px, ch, figure_attr)
                    except curses.error:
                        pass

        # BPM pill below figure
        bpm_str = f" ♪ {int(bpm)} BPM "
        by = start_y + pose_h + 1
        bx = w // 2 - len(bpm_str) // 2
        if 0 <= by < h and 0 <= bx < w:
            try:
                self.win.addstr(by, bx, bpm_str, curses.color_pair(_WHITE) | curses.A_BOLD)
            except curses.error:
                pass

    # ----------------------------------------------------------------------- #
    #  Shared helper                                                           #
    # ----------------------------------------------------------------------- #

    def _draw_ripple_inner(self, h: int, w: int, bp: float, volume: float) -> None:
        """Low-level ripple used as background layer by other modes."""
        cx, cy = w / 2.0, h / 2.0
        aspect = 2.2
        for y in range(h):
            for x in range(w):
                dx = (x - cx) / cx
                dy = (y - cy) / cy * aspect
                d  = math.sqrt(dx * dx + dy * dy) / (aspect * 0.9)
                i  = math.exp(-(d - bp) ** 2 * 18.0) * volume * math.exp(-d * 0.9)
                i  = max(0.0, min(1.0, i))
                if i < 0.05:
                    continue
                char = _DENSITY[int(i * (len(_DENSITY) - 1))]
                hue  = int((bp * self.num_colors + d * 2) % self.num_colors)
                try:
                    self.win.addch(y, x, char, curses.color_pair(hue + 1))
                except curses.error:
                    pass

    # ----------------------------------------------------------------------- #
    #  Info bar                                                                #
    # ----------------------------------------------------------------------- #

    def _draw_info(self, h: int, w: int, mode_name: str) -> None:
        deck   = self.state.active_deck()
        bp     = self.state.beat_phase()
        bpm    = deck.bpm
        status = "▶" if deck.playing else "■"
        bpm_s  = f"{bpm:.1f} BPM" if bpm > 0 else "--- BPM"

        pos_s = ""
        if deck.duration > 0 and deck.position > 0:
            e = int(deck.position * deck.duration)
            total = int(deck.duration)
            pos_s = f"  {e//60}:{e%60:02d}/{total//60}:{total%60:02d}"

        title = deck.title
        max_t = w - len(bpm_s) - len(pos_s) - 14
        if len(title) > max_t:
            title = title[:max_t - 1] + "…"

        info = f" {status} {title}  {bpm_s}{pos_s}  [{mode_name}]"
        info = info[: w - 1]
        hint = " q=quit  m=mode  +/-=brightness"[: w - 1]

        on_beat = bp < 0.08 or bp > 0.92
        info_attr = (
            curses.color_pair(_WHITE) | curses.A_BOLD if on_beat
            else curses.color_pair(_CYAN)
        )

        try:
            self.win.addstr(h - 3, 0, "─" * (w - 1), curses.color_pair(_BLUE))
            self.win.addstr(h - 2, 0, info.ljust(w - 1), info_attr)
            self.win.addstr(h - 1, 0, hint, curses.color_pair(_BLUE))
        except curses.error:
            pass
