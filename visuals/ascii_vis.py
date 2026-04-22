"""
ASCII art visualiser — 6 modes driven by MusicState.

Renders to any Canvas backend (terminal or Qt window).

Keys:
  m      — cycle mode
  +/-    — brightness
  q/ESC  — quit  (terminal mode only; Qt window has its own close button)
"""

import math
import random
import time
from dataclasses import dataclass

import numpy as np

from state import MusicState
from visuals.canvas import Canvas, BLUE, CYAN, GREEN, YELLOW, RED, MAGENTA, WHITE

TARGET_FPS = 30

# --------------------------------------------------------------------------- #
#  Character palettes                                                           #
# --------------------------------------------------------------------------- #

_DENSITY  = " .,:;!|*#@"
_FIRE_CH  = " .,:;+=xX$&#"
_MATRIX_CH = (
    "ｦｧｨｩｪｫｬｭｮｯｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝ"
    "0123456789@#$%&"
)
_SPARK_CH = "*+.oO@#x~"

# --------------------------------------------------------------------------- #
#  Dancer poses  (6 rows × ~12 chars, centred on screen)                      #
# --------------------------------------------------------------------------- #

DANCER_POSES = [
    [r"   \\ O //  ", r"    \\|//   ", r"     |      ",
     r"   --|--    ", r"    / \     ", r"   /   \    "],
    [r"     O      ", r"    /|\     ", r"     |      ",
     r"     |      ", r"    / \     ", r"   /   \    "],
    [r"     O      ", r"     |\     ", r"    /|      ",
     r"     |      ", r"    /|\     ", r"   /   \    "],
    [r"     O      ", r"    \|/     ", r"     |      ",
     r"    / \     ", r"   /   \    ", r"  /     \   "],
    [r"     O      ", r"    /|      ", r"     |\     ",
     r"     |      ", r"    /|\     ", r"   /   \    "],
    [r"   \oO/     ", r"     |      ", r"    /|\     ",
     r"     |      ", r"    / \     ", r"   /   \    "],
    [r"\   O   /   ", r" \  |  /    ", r"   \|/      ",
     r"    |       ", r"   / \      ", r"  /   \     "],
    [r"     O      ", r"     |\     ", r"    /|      ",
     r"   / |      ", r"  /  |      ", r"      \     "],
]

# --------------------------------------------------------------------------- #
#  Particle                                                                    #
# --------------------------------------------------------------------------- #

@dataclass
class _Particle:
    x: float; y: float
    vx: float; vy: float
    char: str; color: int
    age: int = 0; max_age: int = 22


# --------------------------------------------------------------------------- #
#  Visualiser                                                                  #
# --------------------------------------------------------------------------- #

class AsciiVisualizer:
    """
    Drive any Canvas with music-reactive ASCII art.

    Terminal mode: call run() — blocks, handles its own event loop.
    Qt mode:       call draw_frame(t) each tick; handle keys externally
                   via next_mode() / adjust_brightness(delta).
    """

    def __init__(self, canvas: Canvas, state: MusicState):
        self.canvas = canvas
        self.state  = state

        self._intensity = 1.0
        self._mode_idx  = 0
        self._modes     = [
            ("ripple",    self._draw_ripple),
            ("plasma",    self._draw_plasma),
            ("matrix",    self._draw_matrix),
            ("fire",      self._draw_fire),
            ("particles", self._draw_particles),
            ("dancer",    self._draw_dancer),
        ]

        self._last_beat_count = 0

        # Per-mode state
        self._matrix_heads  = None
        self._matrix_speeds = None
        self._matrix_lens   = None
        self._matrix_chars  = None
        self._fire_buf      = None
        self._particles: list[_Particle] = []
        self._dancer_frame  = 0

    # ----------------------------------------------------------------------- #
    #  Public control API (used by Qt key handler)                            #
    # ----------------------------------------------------------------------- #

    def next_mode(self) -> None:
        self._mode_idx = (self._mode_idx + 1) % len(self._modes)
        self._matrix_heads = None
        self._fire_buf = None

    def adjust_brightness(self, delta: float) -> None:
        self._intensity = max(0.1, min(2.0, self._intensity + delta))

    def current_mode_name(self) -> str:
        return self._modes[self._mode_idx][0]

    # ----------------------------------------------------------------------- #
    #  Terminal main loop                                                      #
    # ----------------------------------------------------------------------- #

    def run(self) -> None:
        """Blocking loop for curses terminal mode."""
        import curses as _curses

        # curses-specific setup that doesn't belong in the canvas
        win = self.canvas._win   # type: ignore[attr-defined]
        _curses.curs_set(0)
        win.nodelay(True)

        frame_dt = 1.0 / TARGET_FPS
        while True:
            t   = time.time()
            key = win.getch()
            if key in (ord("q"), 27):
                break
            elif key == ord("m"):
                self.next_mode()
            elif key in (ord("+"), ord("=")):
                self.adjust_brightness(+0.1)
            elif key == ord("-"):
                self.adjust_brightness(-0.1)

            self.draw_frame(t)

            sleep = frame_dt - (time.time() - t)
            if sleep > 0:
                time.sleep(sleep)

    # ----------------------------------------------------------------------- #
    #  Single frame (used by both terminal loop and Qt timer)                 #
    # ----------------------------------------------------------------------- #

    def draw_frame(self, t: float) -> None:
        if self.state.beat_count != self._last_beat_count:
            self._on_beat()
            self._last_beat_count = self.state.beat_count

        self.canvas.erase()
        h, w = self.canvas.size()
        vis_h = max(h - 3, 1)

        name, draw_fn = self._modes[self._mode_idx]
        draw_fn(vis_h, w, t)
        self._draw_info(h, w, name)
        self.canvas.refresh()

    # ----------------------------------------------------------------------- #
    #  Beat event                                                              #
    # ----------------------------------------------------------------------- #

    def _on_beat(self) -> None:
        self._dancer_frame = (self._dancer_frame + 1) % len(DANCER_POSES)
        self._spawn_particles()

    # ----------------------------------------------------------------------- #
    #  Mode: ripple                                                            #
    # ----------------------------------------------------------------------- #

    def _draw_ripple(self, h: int, w: int, t: float) -> None:
        bp     = self.state.beat_phase()
        volume = max(self.state.deck1.volume, 0.04) * self._intensity
        self._draw_ripple_inner(h, w, bp, volume)

    def _draw_ripple_inner(self, h: int, w: int, bp: float, volume: float) -> None:
        cx, cy = w / 2.0, h / 2.0
        aspect = 2.2
        nc     = self.canvas.size()[1]   # unused but kept for compat
        chars  = _DENSITY

        for y in range(h):
            for x in range(w):
                dx = (x - cx) / cx
                dy = (y - cy) / cy * aspect
                d  = math.sqrt(dx*dx + dy*dy) / (aspect * 0.9)
                i  = math.exp(-(d - bp)**2 * 18.0)
                hp = (bp * 2) % 1.0
                i += math.exp(-(d - hp)**2 * 28.0) * 0.45
                i *= volume * math.exp(-d * 0.9)
                i  = max(0.0, min(1.0, i))
                if i < 0.02:
                    continue
                char  = chars[int(i * (len(chars) - 1))]
                hue   = int((bp * 7 + d * 2) % 7)
                self.canvas.put(y, x, char, hue + 1, i > 0.55)

    # ----------------------------------------------------------------------- #
    #  Mode: plasma                                                            #
    # ----------------------------------------------------------------------- #

    def _draw_plasma(self, h: int, w: int, t: float) -> None:
        bp     = self.state.beat_phase()
        volume = max(self.state.deck1.volume, 0.05) * self._intensity
        bpm    = self.state.deck1.bpm or 120.0
        mt     = t * (bpm / 120.0) * 0.4
        flash  = math.exp(-bp * 4.0) * 0.35

        x = np.linspace(-3.0, 3.0, w)
        y = np.linspace(-2.0, 2.0, h)
        X, Y = np.meshgrid(x, y)
        R = np.sqrt(X**2 + Y**2)
        Z = (np.sin(X + mt) + np.sin(Y + mt*0.9)
             + np.sin((X+Y)*0.5 + mt*0.7) + np.sin(R + mt))

        intensity = np.clip((Z + 4)/8 * (0.4 + volume) + flash, 0.0, 1.0)
        hue_map   = ((Z*1.5 + mt*2) % 7).astype(int) % 7
        chars     = _DENSITY
        nc        = len(chars)

        for row in range(h):
            for col in range(w):
                iv   = intensity[row, col]
                char = chars[int(iv * (nc - 1))]
                self.canvas.put(row, col, char, int(hue_map[row, col]) + 1, iv > 0.6)

    # ----------------------------------------------------------------------- #
    #  Mode: matrix rain                                                       #
    # ----------------------------------------------------------------------- #

    def _draw_matrix(self, h: int, w: int, t: float) -> None:
        if self._matrix_heads is None or len(self._matrix_heads) != w:
            self._matrix_heads  = np.random.uniform(-h, 0, w)
            self._matrix_speeds = np.random.uniform(0.4, 1.2, w)
            self._matrix_lens   = np.random.randint(6, 24, w)
            self._matrix_chars  = [
                [random.choice(_MATRIX_CH) for _ in range(h + 30)]
                for _ in range(w)
            ]

        bp     = self.state.beat_phase()
        bpm    = self.state.deck1.bpm or 120.0
        volume = max(self.state.deck1.volume, 0.15) * self._intensity

        self._matrix_heads += self._matrix_speeds * (bpm / 60.0) * volume * 3.0 / TARGET_FPS

        for c in range(w):
            if self._matrix_heads[c] > h + self._matrix_lens[c]:
                self._matrix_heads[c]  = -self._matrix_lens[c]
                self._matrix_speeds[c] = random.uniform(0.4, 1.2)
                self._matrix_lens[c]   = random.randint(6, 24)
                self._matrix_chars[c]  = [random.choice(_MATRIX_CH) for _ in range(h + 30)]

        on_beat = bp < 0.1
        for c in range(w):
            head = int(self._matrix_heads[c])
            ln   = self._matrix_lens[c]
            col_chars = self._matrix_chars[c]
            for r in range(max(0, head - ln), min(h, head + 1)):
                age  = head - r
                frac = age / max(ln, 1)
                if age == 0:
                    char, color, bold = random.choice(_MATRIX_CH), WHITE, True
                elif frac < 0.25:
                    char, color, bold = col_chars[r % len(col_chars)], GREEN, True
                elif frac < 0.6:
                    char, color, bold = col_chars[r % len(col_chars)], GREEN, False
                else:
                    char, color, bold = col_chars[r % len(col_chars)], CYAN, False
                self.canvas.put(r, c, char, color, bold or on_beat)

    # ----------------------------------------------------------------------- #
    #  Mode: fire                                                              #
    # ----------------------------------------------------------------------- #

    def _draw_fire(self, h: int, w: int, t: float) -> None:
        if self._fire_buf is None or self._fire_buf.shape != (h + 2, w):
            self._fire_buf = np.zeros((h + 2, w), dtype=np.float32)

        bp     = self.state.beat_phase()
        volume = max(self.state.deck1.volume, 0.1) * self._intensity
        heat   = volume * (0.6 + 0.4 * math.exp(-bp * 3.0))

        self._fire_buf[h+1, :] = np.random.uniform(
            max(0.0, heat - 0.15), min(1.0, heat + 0.05), w
        ).astype(np.float32)

        self._fire_buf[:h, :] = (
            self._fire_buf[1:h+1, :]
            + np.roll(self._fire_buf[1:h+1, :],  1, axis=1)
            + np.roll(self._fire_buf[1:h+1, :], -1, axis=1)
            + self._fire_buf[2:h+2, :]
        ) * 0.25 * 0.96

        chars = _FIRE_CH
        nc    = len(chars)
        buf   = self._fire_buf

        for row in range(h):
            for col in range(w):
                v    = float(buf[row, col])
                char = chars[int(v * (nc - 1))]
                if v < 0.25:
                    color, bold = RED, False
                elif v < 0.55:
                    color, bold = RED, True
                elif v < 0.80:
                    color, bold = YELLOW, True
                else:
                    color, bold = WHITE, True
                self.canvas.put(row, col, char, color, bold)

    # ----------------------------------------------------------------------- #
    #  Mode: particles                                                         #
    # ----------------------------------------------------------------------- #

    def _spawn_particles(self) -> None:
        h, w   = self.canvas.size()
        cx, cy = w // 2, (h - 3) // 2
        vol    = max(self.state.deck1.volume, 0.3) * self._intensity
        for _ in range(int(20 + vol * 40)):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(0.4, 2.2) * (0.5 + vol)
            self._particles.append(_Particle(
                x=float(cx), y=float(cy),
                vx=math.cos(angle) * speed,
                vy=math.sin(angle) * speed * 0.5,
                char=random.choice(_SPARK_CH),
                color=random.randint(1, 7),
                max_age=int(14 + random.uniform(0, 14)),
            ))

    def _draw_particles(self, h: int, w: int, t: float) -> None:
        bp     = self.state.beat_phase()
        volume = max(self.state.deck1.volume, 0.04) * self._intensity * 0.25
        self._draw_ripple_inner(h, w, bp, volume)

        alive: list[_Particle] = []
        for p in self._particles:
            p.x += p.vx; p.y += p.vy; p.vy += 0.04; p.age += 1
            if p.age < p.max_age and 0 <= int(p.y) < h and 0 <= int(p.x) < w:
                fade = 1.0 - p.age / p.max_age
                self.canvas.put(int(p.y), int(p.x), p.char, p.color, fade > 0.5)
                alive.append(p)
        self._particles = alive

    # ----------------------------------------------------------------------- #
    #  Mode: dancer                                                            #
    # ----------------------------------------------------------------------- #

    def _draw_dancer(self, h: int, w: int, t: float) -> None:
        bp     = self.state.beat_phase()
        volume = max(self.state.deck1.volume, 0.05) * self._intensity
        bpm    = self.state.deck1.bpm or 120.0
        mt     = t * (bpm / 120.0) * 0.4

        # Plasma background at low intensity
        x = np.linspace(-3.0, 3.0, w)
        y = np.linspace(-2.0, 2.0, h)
        X, Y = np.meshgrid(x, y)
        Z    = np.sin(X + mt) + np.sin(Y + mt*0.9) + np.sin(np.sqrt(X**2+Y**2) + mt)
        ibg  = np.clip((Z + 3)/6 * volume * 0.35, 0.0, 1.0)
        hbg  = ((Z + mt) % 7).astype(int) % 7
        chars = _DENSITY
        nc    = len(chars)
        for row in range(h):
            for col in range(w):
                iv = ibg[row, col]
                if iv < 0.05:
                    continue
                self.canvas.put(row, col, chars[int(iv*(nc-1))], int(hbg[row,col])+1, False)

        # Dancer
        pose   = DANCER_POSES[self._dancer_frame % len(DANCER_POSES)]
        pose_h = len(pose)
        pose_w = max(len(r) for r in pose)
        sy     = h // 2 - pose_h // 2
        sx     = w // 2 - pose_w // 2
        on_beat = bp < 0.15
        color   = WHITE if on_beat else (int(bp * 7) % 7) + 1
        for ri, row in enumerate(pose):
            py = sy + ri
            if not (0 <= py < h):
                continue
            for ci, ch in enumerate(row):
                px = sx + ci
                if 0 <= px < w and ch not in (" ", "\t"):
                    self.canvas.put(py, px, ch, color, True)

        bpm_str = f" \u266a {int(bpm)} BPM "
        by = sy + pose_h + 1
        bx = w // 2 - len(bpm_str) // 2
        if 0 <= by < h:
            self.canvas.puts(by, bx, bpm_str, WHITE, True)

    # ----------------------------------------------------------------------- #
    #  Info bar                                                                #
    # ----------------------------------------------------------------------- #

    def _draw_info(self, h: int, w: int, mode_name: str) -> None:
        deck   = self.state.active_deck()
        bp     = self.state.beat_phase()
        bpm    = deck.bpm
        status = "\u25b6" if deck.playing else "\u25a0"
        bpm_s  = f"{bpm:.1f} BPM" if bpm > 0 else "--- BPM"

        pos_s = ""
        if deck.duration > 0 and deck.position > 0:
            e = int(deck.position * deck.duration)
            tot = int(deck.duration)
            pos_s = f"  {e//60}:{e%60:02d}/{tot//60}:{tot%60:02d}"

        title = deck.title
        max_t = w - len(bpm_s) - len(pos_s) - 14
        if len(title) > max_t:
            title = title[:max_t-1] + "\u2026"

        info = f" {status} {title}  {bpm_s}{pos_s}  [{mode_name}]"
        hint = " q=quit  m=mode  +/-=brightness"

        on_beat = bp < 0.08 or bp > 0.92
        ic = WHITE if on_beat else CYAN
        ib = on_beat

        self.canvas.puts(h-3, 0, "\u2500" * (w-1), BLUE, False)
        self.canvas.puts(h-2, 0, info[:w-1].ljust(w-1), ic, ib)
        self.canvas.puts(h-1, 0, hint[:w-1], BLUE, False)
