"""
Curses backend for Canvas.
"""

import curses
from visuals.canvas import Canvas, BLUE, CYAN, GREEN, YELLOW, RED, MAGENTA, WHITE

import curses as _curses

_CURSES_COLORS = [
    None,                    # index 0 unused
    _curses.COLOR_BLUE,
    _curses.COLOR_CYAN,
    _curses.COLOR_GREEN,
    _curses.COLOR_YELLOW,
    _curses.COLOR_RED,
    _curses.COLOR_MAGENTA,
    _curses.COLOR_WHITE,
]


def setup_curses_colors() -> None:
    _curses.start_color()
    try:
        _curses.use_default_colors()
        bg = -1
    except Exception:
        bg = _curses.COLOR_BLACK
    for i, fg in enumerate(_CURSES_COLORS[1:], start=1):
        _curses.init_pair(i, fg, bg)


class CursesCanvas(Canvas):
    def __init__(self, win):
        self._win = win

    def size(self) -> tuple[int, int]:
        return self._win.getmaxyx()

    def put(self, row: int, col: int, char: str,
            color: int = WHITE, bold: bool = False) -> None:
        attr = _curses.color_pair(color)
        if bold:
            attr |= _curses.A_BOLD
        try:
            self._win.addch(row, col, char, attr)
        except _curses.error:
            pass

    def puts(self, row: int, col: int, text: str,
             color: int = WHITE, bold: bool = False) -> None:
        attr = _curses.color_pair(color)
        if bold:
            attr |= _curses.A_BOLD
        try:
            self._win.addstr(row, col, text, attr)
        except _curses.error:
            pass

    def erase(self) -> None:
        self._win.erase()

    def refresh(self) -> None:
        self._win.refresh()
