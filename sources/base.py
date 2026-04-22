"""
Abstract DataSource interface.

Option 1  →  OscDataSource        (sources/osc.py)   — this file
Option 2  →  ControlProxySource   (sources/control_proxy.py)  — future
Option 3  →  embed renderer in Mixxx Qt process; no separate source needed

Swapping implementations requires only changing the import in main.py.
The renderer (visuals/) never touches this directly.
"""

from abc import ABC, abstractmethod
from state import MusicState


class DataSource(ABC):
    @abstractmethod
    def start(self, state: MusicState) -> None:
        """Begin feeding data into *state*. Should be non-blocking (spawn a thread)."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Clean shutdown."""
        ...
