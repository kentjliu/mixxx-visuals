"""
Qt window — GLSL shader background + ASCII overlay.

The OpenGL widget renders a full-screen fragment shader each frame.
QPainter then draws the dancer figure and info bar on top.

Keys:  m=mode  f=fullscreen  t=always-on-top  +/-=brightness  q/ESC=quit

Architecture note (Option 3 migration):
  Replace QMainWindow with a QWidget parented to Mixxx's own window.
  ShaderWidget is self-contained and needs only MusicState.
"""

import time
from collections import defaultdict

import moderngl
import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QSurfaceFormat
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtWidgets import QApplication, QMainWindow

from state import MusicState
from visuals.shaders import VERT, FRAG_BY_MODE, MODE_NAMES
from visuals.ascii_vis import DANCER_POSES, AsciiVisualizer

# ─────────────────────────────────────────────────────────────────────────────
#  Overlay colour palette (for QPainter text drawn over the shader)
# ─────────────────────────────────────────────────────────────────────────────

_OVERLAY_COLORS = [
    None,
    QColor(80,   80,  255),   # BLUE
    QColor(0,   255,  255),   # CYAN
    QColor(0,   255,    0),   # GREEN
    QColor(255, 255,    0),   # YELLOW
    QColor(255,  60,   60),   # RED
    QColor(255,   0,  255),   # MAGENTA
    QColor(255, 255,  255),   # WHITE
]


# ─────────────────────────────────────────────────────────────────────────────
#  QtCanvas  (kept for the terminal→Qt migration path; not used by shaders)
# ─────────────────────────────────────────────────────────────────────────────

from visuals.canvas import Canvas, WHITE

class QtCanvas(Canvas):
    def __init__(self, rows: int = 40, cols: int = 100):
        self._rows = rows; self._cols = cols
        self._chars  = np.full((rows, cols), " ", dtype="U1")
        self._colors = np.zeros((rows, cols), dtype=np.uint8)
        self._bolds  = np.zeros((rows, cols), dtype=bool)

    def resize(self, rows, cols):
        self._rows = rows; self._cols = cols
        self._chars  = np.full((rows, cols), " ", dtype="U1")
        self._colors = np.zeros((rows, cols), dtype=np.uint8)
        self._bolds  = np.zeros((rows, cols), dtype=bool)

    def size(self): return self._rows, self._cols

    def put(self, row, col, char, color=WHITE, bold=False):
        if 0 <= row < self._rows and 0 <= col < self._cols:
            self._chars[row, col]  = char[0] if char else " "
            self._colors[row, col] = color
            self._bolds[row, col]  = bold

    def erase(self):
        self._chars[:] = " "; self._colors[:] = 0; self._bolds[:] = False

    def snapshot(self):
        return self._chars.copy(), self._colors.copy(), self._bolds.copy()


# ─────────────────────────────────────────────────────────────────────────────
#  Shader widget
# ─────────────────────────────────────────────────────────────────────────────

class ShaderWidget(QOpenGLWidget):
    def __init__(self, state: MusicState, parent=None):
        super().__init__(parent)
        self.state = state

        self._mode_idx     = 0
        self._intensity    = 1.0
        self._dancer_frame = 0
        self._last_beat    = 0
        self._start        = time.time()
        self._ascii_mode   = False

        # Monospace font for overlay
        for name in ("Menlo", "Monaco", "Consolas", "Courier New", "Courier"):
            f = QFont(name, 15)
            if QFontMetrics(f).averageCharWidth() > 0:
                self._font = f
                break
        self._font_large = QFont(self._font.family(), 26)
        self._font_bold  = QFont(self._font.family(), 15)
        self._font_bold.setBold(True)

        # ASCII visualiser (shares the same state; QtCanvas sized dynamically)
        self._qt_canvas = QtCanvas()
        self._ascii_vis = AsciiVisualizer(self._qt_canvas, state)

        self._ctx      = None
        self._programs = {}
        self._vao      = None

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        timer = QTimer(self)
        timer.timeout.connect(self.update)
        timer.start(1000 // 30)

    # ── OpenGL lifecycle ────────────────────────────────────────────────────

    def initializeGL(self):
        try:
            self._ctx = moderngl.create_context()
        except Exception as e:
            print(f"[shader] moderngl init failed: {e}")
            return

        # Full-screen quad (triangle strip)
        verts = np.array([-1,-1, 1,-1, -1,1, 1,1], dtype="f4")
        vbo   = self._ctx.buffer(verts.tobytes())

        for name, frag in FRAG_BY_MODE.items():
            try:
                prog = self._ctx.program(vertex_shader=VERT, fragment_shader=frag)
                vao  = self._ctx.vertex_array(prog, [(vbo, "2f", "in_vert")])
                self._programs[name] = (prog, vao)
            except Exception as e:
                print(f"[shader] compile failed for '{name}': {e}")

    def resizeGL(self, w, h):
        if self._ctx:
            self._ctx.viewport = (0, 0, w, h)

    def paintGL(self):
        """All rendering happens here — both GL shader and QPainter overlay.

        Qt requires QPainter to be used inside paintGL() on QOpenGLWidget;
        starting it in paintEvent() would clear the framebuffer first.
        """
        if self._ascii_mode:
            self._paint_ascii()
            return

        if self._ctx is None:
            return

        t = time.time() - self._start

        if self.state.beat_count != self._last_beat:
            self._dancer_frame = (self._dancer_frame + 1) % len(DANCER_POSES)
            self._last_beat = self.state.beat_count

        mode_name = MODE_NAMES[self._mode_idx]
        if mode_name not in self._programs:
            return

        prog, vao = self._programs[mode_name]
        deck      = self.state.active_deck()
        bp        = self.state.beat_phase()

        # QOpenGLWidget renders into an internal FBO, not FBO 0.
        # Tell moderngl to target that FBO so output reaches the screen.
        fbo = self._ctx.detect_framebuffer(self.defaultFramebufferObject())
        fbo.use()

        def _set(u, v):
            if u in prog:
                prog[u].value = v

        _set("u_resolution", (float(self.width()), float(self.height())))
        _set("u_time",   t)
        _set("u_beat",   bp)
        _set("u_bpm",    deck.bpm or 120.0)
        _set("u_volume", min(deck.volume * self._intensity, 1.0))
        _set("u_bass",   min(self.state.bass  * self._intensity, 1.0))
        _set("u_mid",    min(self.state.mid   * self._intensity, 1.0))
        _set("u_high",   min(self.state.high  * self._intensity, 1.0))

        self._ctx.clear(0.0, 0.0, 0.0)
        vao.render(moderngl.TRIANGLE_STRIP)

        # QPainter overlay — must be started inside paintGL() on QOpenGLWidget
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self._draw_overlay(painter, mode_name, bp, deck)
        painter.end()

    # ── ASCII mode ──────────────────────────────────────────────────────────

    def _paint_ascii(self) -> None:
        """Render the ASCII visualiser via QPainter (no GL shader)."""
        fm = QFontMetrics(self._font)
        cw = fm.averageCharWidth()
        ch = fm.height()
        cols = max(1, self.width()  // cw)
        rows = max(1, self.height() // ch)
        self._qt_canvas.resize(rows, cols)

        self._ascii_vis.draw_frame(time.time() - self._start)
        chars, colors, bolds = self._qt_canvas.snapshot()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.fillRect(0, 0, self.width(), self.height(), QColor(0, 0, 0))

        for row in range(rows):
            y = row * ch + fm.ascent()
            for col in range(cols):
                char = chars[row, col]
                if char == " ":
                    continue
                cidx  = int(colors[row, col])
                color = _OVERLAY_COLORS[cidx] if 0 < cidx < len(_OVERLAY_COLORS) else QColor(255, 255, 255)
                if color is None:
                    color = QColor(255, 255, 255)
                painter.setFont(self._font_bold if bolds[row, col] else self._font)
                painter.setPen(color)
                painter.drawText(col * cw, y, char)

        painter.end()

    # ── Overlay ─────────────────────────────────────────────────────────────

    def _draw_overlay(self, p: QPainter, mode: str, bp: float, deck) -> None:
        w, h = self.width(), self.height()

        if mode == "dancer":
            self._draw_dancer(p, bp, deck)

        self._draw_info(p, w, h, mode, bp, deck)

    def _draw_dancer(self, p: QPainter, bp: float, deck) -> None:
        pose   = DANCER_POSES[self._dancer_frame % len(DANCER_POSES)]
        p.setFont(self._font_large)
        fm     = QFontMetrics(self._font_large)
        cw, ch = fm.averageCharWidth(), fm.height()

        pose_px_w = max(len(row) for row in pose) * cw
        pose_px_h = len(pose) * ch

        sx = (self.width()  - pose_px_w) // 2
        sy = (self.height() - pose_px_h) // 2

        on_beat = bp < 0.15
        color   = QColor(255, 255, 255) if on_beat else _OVERLAY_COLORS[
            (int(bp * 6) % 6) + 1
        ]
        p.setPen(color)

        for ri, row in enumerate(pose):
            y = sy + ri * ch + fm.ascent()
            for ci, ch_char in enumerate(row):
                if ch_char not in (" ", "\t"):
                    p.drawText(sx + ci * cw, y, ch_char)

        if deck.bpm > 0:
            bpm_str = f"♪ {int(deck.bpm)} BPM"
            p.setFont(self._font)
            fm2  = QFontMetrics(self._font)
            bx   = (self.width() - fm2.horizontalAdvance(bpm_str)) // 2
            by   = sy + pose_px_h + fm2.height()
            p.setPen(QColor(255, 255, 255))
            p.drawText(bx, by, bpm_str)

    def _draw_info(self, p: QPainter, w: int, h: int,
                   mode: str, bp: float, deck) -> None:
        p.setFont(self._font)
        fm   = QFontMetrics(self._font)
        lh   = fm.height()

        status = "▶" if deck.playing else "■"
        bpm_s  = f"{deck.bpm:.1f} BPM" if deck.bpm > 0 else "--- BPM"
        pos_s  = ""
        if deck.duration > 0 and deck.position > 0:
            e = int(deck.position * deck.duration)
            tot = int(deck.duration)
            pos_s = f"  {e//60}:{e%60:02d}/{tot//60}:{tot%60:02d}"

        info = f" {status} {deck.title}  {bpm_s}{pos_s}  [{mode}]"
        hint = " m=mode  a=ascii  f=fullscreen  t=on-top  +/-=brightness  q=quit"

        # Semi-transparent black bar at the bottom
        from PyQt6.QtGui import QColor as QC
        p.fillRect(0, h - lh * 2 - 6, w, lh * 2 + 6, QC(0, 0, 0, 160))

        on_beat = bp < 0.08 or bp > 0.92
        p.setPen(QColor(255, 255, 255) if on_beat else QColor(0, 200, 200))
        p.drawText(4, h - lh - 4 + fm.ascent() - lh, info)
        p.setPen(QColor(80, 80, 120))
        p.drawText(4, h - 4 + fm.ascent() - lh, hint)

    # ── Key handling ────────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        k = event.key()
        if k == Qt.Key.Key_A:
            self._ascii_mode = not self._ascii_mode
        elif k == Qt.Key.Key_M:
            if self._ascii_mode:
                self._ascii_vis.next_mode()
            else:
                self._mode_idx = (self._mode_idx + 1) % len(MODE_NAMES)
        elif k in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            if self._ascii_mode:
                self._ascii_vis.adjust_brightness(+0.1)
            else:
                self._intensity = min(2.0, self._intensity + 0.1)
        elif k == Qt.Key.Key_Minus:
            if self._ascii_mode:
                self._ascii_vis.adjust_brightness(-0.1)
            else:
                self._intensity = max(0.1, self._intensity - 0.1)
        elif k in (Qt.Key.Key_Q, Qt.Key.Key_Escape):
            self.window().close()
        elif k == Qt.Key.Key_F:
            win = self.window()
            win.showNormal() if win.isFullScreen() else win.showFullScreen()
        elif k == Qt.Key.Key_T:
            win   = self.window()
            flags = win.windowFlags()
            win.setWindowFlags(flags ^ Qt.WindowType.WindowStaysOnTopHint)
            win.show()


# ─────────────────────────────────────────────────────────────────────────────
#  Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def run_qt_window(state: MusicState) -> None:
    """Launch the shader window.  Blocks until closed.

    Note: QSurfaceFormat must be configured by the caller (main.py)
    BEFORE this function is imported, i.e. before QApplication is created.
    """
    app    = QApplication.instance() or QApplication([])
    app.setApplicationName("Mixxx Visuals")

    win    = QMainWindow()
    widget = ShaderWidget(state)
    win.setCentralWidget(widget)
    win.setWindowTitle("Mixxx Visuals  —  m=mode  f=fullscreen  t=on-top")
    win.resize(960, 600)
    win.setStyleSheet("background: black;")
    win.show()
    widget.setFocus()

    app.exec()
