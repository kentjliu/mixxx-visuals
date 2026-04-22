"""
Qt window backend for the ASCII visualiser.

Opens a standalone resizable window — no terminal needed.
The same AsciiVisualizer code runs on top of a QtCanvas that
renders each character with QPainter using a monospace font.

Keys:
  m        cycle visual mode
  +/-      brightness
  f        toggle fullscreen
  t        toggle always-on-top  (useful as a DJ overlay)
  q/ESC    close

This is also the architectural bridge to Option 3 (embedding directly
inside Mixxx): replace QMainWindow with a QWidget parented to Mixxx's
main window, and remove the standalone QApplication.
"""

import time
from collections import defaultdict

import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QFontMetrics
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget

from visuals.canvas import Canvas, WHITE

# --------------------------------------------------------------------------- #
#  Colour palette  (dim and bold variants)                                    #
# --------------------------------------------------------------------------- #
#  Indices 1–7 match canvas.py constants BLUE…WHITE.

_DIM = [
    None,                       # 0 unused
    QColor(60,  60,  180),      # BLUE
    QColor(0,   180, 180),      # CYAN
    QColor(0,   180, 0),        # GREEN
    QColor(180, 180, 0),        # YELLOW
    QColor(180, 0,   0),        # RED
    QColor(180, 0,   180),      # MAGENTA
    QColor(200, 200, 200),      # WHITE
]

_BOLD = [
    None,
    QColor(80,  80,  255),      # BLUE bold
    QColor(0,   255, 255),      # CYAN bold
    QColor(0,   255, 0),        # GREEN bold
    QColor(255, 255, 0),        # YELLOW bold
    QColor(255, 60,  60),       # RED bold
    QColor(255, 0,   255),      # MAGENTA bold
    QColor(255, 255, 255),      # WHITE bold
]

_BG = QColor(0, 0, 0)

# --------------------------------------------------------------------------- #
#  QtCanvas — buffer that AsciiVisualizer writes into                         #
# --------------------------------------------------------------------------- #

class QtCanvas(Canvas):
    """
    In-memory character grid.  AsciiVisualizer writes here; the Qt
    widget reads it in paintEvent().
    """

    def __init__(self, rows: int = 40, cols: int = 100):
        self._rows = rows
        self._cols = cols
        self._chars  = np.full((rows, cols), " ", dtype="U1")
        self._colors = np.zeros((rows, cols), dtype=np.uint8)
        self._bolds  = np.zeros((rows, cols), dtype=bool)

    def resize(self, rows: int, cols: int) -> None:
        self._rows = rows
        self._cols = cols
        self._chars  = np.full((rows, cols), " ", dtype="U1")
        self._colors = np.zeros((rows, cols), dtype=np.uint8)
        self._bolds  = np.zeros((rows, cols), dtype=bool)

    def size(self) -> tuple[int, int]:
        return self._rows, self._cols

    def put(self, row: int, col: int, char: str,
            color: int = WHITE, bold: bool = False) -> None:
        if 0 <= row < self._rows and 0 <= col < self._cols:
            self._chars[row, col]  = char[0] if char else " "
            self._colors[row, col] = color
            self._bolds[row, col]  = bold

    def puts(self, row: int, col: int, text: str,
             color: int = WHITE, bold: bool = False) -> None:
        for i, ch in enumerate(text):
            self.put(row, col + i, ch, color, bold)

    def erase(self) -> None:
        self._chars[:]  = " "
        self._colors[:] = 0
        self._bolds[:]  = False

    def snapshot(self):
        """Return buffer copies for the paint thread."""
        return self._chars.copy(), self._colors.copy(), self._bolds.copy()


# --------------------------------------------------------------------------- #
#  Qt widget                                                                   #
# --------------------------------------------------------------------------- #

class _VisualsWidget(QWidget):
    def __init__(self, canvas: QtCanvas, visualizer):
        super().__init__()
        self._canvas     = canvas
        self._visualizer = visualizer

        # Monospace font
        for name in ("Menlo", "Monaco", "Consolas", "Courier New", "Courier"):
            f = QFont(name, 13)
            if QFontMetrics(f).averageCharWidth() > 0:
                self._font = f
                break

        fm             = QFontMetrics(self._font)
        self._cw       = fm.averageCharWidth()
        self._ch       = fm.height()
        self._baseline = fm.ascent()

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # 30 fps render timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000 // 30)

    def _tick(self) -> None:
        h, w = self._canvas.size()
        new_rows = max(1, self.height() // self._ch)
        new_cols = max(1, self.width()  // self._cw)
        if new_rows != h or new_cols != w:
            self._canvas.resize(new_rows, new_cols)
        self._visualizer.draw_frame(time.time())
        self.update()   # schedule paintEvent

    def paintEvent(self, event) -> None:  # noqa: N802
        chars, colors, bolds = self._canvas.snapshot()
        rows, cols = chars.shape

        painter = QPainter(self)
        painter.fillRect(self.rect(), _BG)
        painter.setFont(self._font)

        # Group by (color, bold) to minimise setPen() calls
        groups: dict[tuple[int, bool], list[tuple[int, int, str]]] = defaultdict(list)
        for row in range(rows):
            y = row * self._ch + self._baseline
            for col in range(cols):
                ch = chars[row, col]
                if ch == " ":
                    continue
                key = (int(colors[row, col]), bool(bolds[row, col]))
                groups[key].append((col * self._cw, y, ch))

        for (cidx, bold), items in groups.items():
            if cidx == 0:
                continue
            palette = _BOLD if bold else _DIM
            qcolor  = palette[cidx] if 1 <= cidx <= 7 else _BOLD[WHITE]
            painter.setPen(qcolor)
            for x, y, ch in items:
                painter.drawText(x, y, ch)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key == Qt.Key.Key_M:
            self._visualizer.next_mode()
        elif key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self._visualizer.adjust_brightness(+0.1)
        elif key == Qt.Key.Key_Minus:
            self._visualizer.adjust_brightness(-0.1)
        elif key in (Qt.Key.Key_Q, Qt.Key.Key_Escape):
            self.window().close()
        elif key == Qt.Key.Key_F:
            w = self.window()
            w.showNormal() if w.isFullScreen() else w.showFullScreen()
        elif key == Qt.Key.Key_T:
            w     = self.window()
            flags = w.windowFlags()
            stay  = Qt.WindowType.WindowStaysOnTopHint
            w.setWindowFlags(flags ^ stay)
            w.show()


# --------------------------------------------------------------------------- #
#  Public entry point                                                          #
# --------------------------------------------------------------------------- #

def run_qt_window(visualizer, canvas: QtCanvas) -> None:
    """
    Launch the Qt window.  Blocks until the window is closed.

    Call after creating your AudioDataSource and AsciiVisualizer:

        canvas = QtCanvas()
        vis    = AsciiVisualizer(canvas, state)
        source.start(state)
        run_qt_window(vis, canvas)
    """
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Mixxx Visuals")

    win    = QMainWindow()
    widget = _VisualsWidget(canvas, visualizer)
    win.setCentralWidget(widget)
    win.setWindowTitle("Mixxx Visuals  —  m=mode  f=fullscreen  t=on-top")
    win.resize(900, 550)
    win.setStyleSheet("background: black;")
    win.show()
    widget.setFocus()

    app.exec()
