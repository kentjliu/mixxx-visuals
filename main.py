"""
Mixxx ASCII Visualiser

  python main.py                      # terminal (curses)
  python main.py --window             # standalone Qt window  ← new
  python main.py --window --device 1  # Qt window + BlackHole input
  python main.py --list-devices       # show audio inputs

macOS loopback setup:
  1. Install BlackHole: https://existential.audio/blackhole/
  2. Audio MIDI Setup → New Multi-Output Device (speakers + BlackHole 2ch)
  3. Mixxx → Preferences → Sound Hardware → Master → Multi-Output Device
  4. python main.py --window --device "BlackHole 2ch"

Window keys:  m=mode  +/-=brightness  f=fullscreen  t=always-on-top  q=quit
"""

import argparse
import sys

from state import MusicState
from sources.audio import AudioDataSource, list_devices
from visuals.ascii_vis import AsciiVisualizer


def run_terminal(args: argparse.Namespace) -> None:
    import curses
    from visuals.curses_canvas import CursesCanvas, setup_curses_colors

    state  = MusicState()
    source = AudioDataSource(device=args.device)
    source.start(state)

    def _main(stdscr):
        setup_curses_colors()
        canvas = CursesCanvas(stdscr)
        vis    = AsciiVisualizer(canvas, state)
        try:
            vis.run()
        finally:
            source.stop()

    try:
        curses.wrapper(_main)
    except KeyboardInterrupt:
        pass


def run_window(args: argparse.Namespace) -> None:
    from visuals.qt_window import QtCanvas, run_qt_window

    state  = MusicState()
    source = AudioDataSource(device=args.device)
    source.start(state)

    canvas = QtCanvas()
    vis    = AsciiVisualizer(canvas, state)
    try:
        run_qt_window(vis, canvas)
    finally:
        source.stop()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mixxx ASCII visualiser",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--window", "-w", action="store_true",
                        help="Open a standalone Qt window instead of using the terminal")
    parser.add_argument("--device", default=None,
                        help='Audio input device name or index (e.g. "BlackHole 2ch" or 1)')
    parser.add_argument("--list-devices", action="store_true",
                        help="List available audio input devices and exit")
    args = parser.parse_args()

    if args.list_devices:
        list_devices()
        return

    if args.window:
        run_window(args)
    else:
        run_terminal(args)


if __name__ == "__main__":
    main()
