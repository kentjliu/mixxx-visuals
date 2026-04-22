"""
Drawing surface abstraction.

AsciiVisualizer writes to a Canvas — the backend (curses terminal or
Qt window) is swapped without touching any visual mode code.

Color index constants (1–7) map to the same palette in both backends:
"""

from abc import ABC, abstractmethod

BLUE    = 1
CYAN    = 2
GREEN   = 3
YELLOW  = 4
RED     = 5
MAGENTA = 6
WHITE   = 7


class Canvas(ABC):
    @abstractmethod
    def size(self) -> tuple[int, int]:
        """Return (rows, cols) of the drawable area."""
        ...

    @abstractmethod
    def put(self, row: int, col: int, char: str,
            color: int = WHITE, bold: bool = False) -> None:
        """Place a single character."""
        ...

    def puts(self, row: int, col: int, text: str,
             color: int = WHITE, bold: bool = False) -> None:
        """Place a string of characters (default: calls put() per char)."""
        for i, ch in enumerate(text):
            self.put(row, col + i, ch, color, bold)

    @abstractmethod
    def erase(self) -> None:
        """Clear the canvas."""
        ...

    def refresh(self) -> None:
        """Flush to screen if the backend needs it (curses does, Qt doesn't)."""
