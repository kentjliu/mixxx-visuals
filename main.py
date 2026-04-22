"""
Mixxx ASCII / Shader Visualiser

  python main.py                      # ASCII art in terminal
  python main.py --window             # GLSL shader window  (default device)
  python main.py --window --device 1  # shader window + BlackHole input
  python main.py --list-devices       # show audio inputs

macOS loopback:
  1. Install BlackHole: https://existential.audio/blackhole/
  2. Audio MIDI Setup → New Multi-Output Device (speakers + BlackHole 2ch)
  3. Mixxx → Preferences → Sound Hardware → Master → Multi-Output Device
  4. python main.py --window --device "BlackHole 2ch"
"""

import argparse

from state import MusicState
from sources.audio import AudioDataSource, list_devices
from visuals.ascii_vis import AsciiVisualizer


def run_terminal(args):
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


def run_window(args):
    # QSurfaceFormat MUST be set before QApplication is created.
    from PyQt6.QtGui import QSurfaceFormat
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    fmt.setDepthBufferSize(24)
    QSurfaceFormat.setDefaultFormat(fmt)

    from visuals.qt_window import run_qt_window

    state  = MusicState()
    source = AudioDataSource(device=args.device)
    source.start(state)
    try:
        run_qt_window(state)
    finally:
        source.stop()


def main():
    parser = argparse.ArgumentParser(
        description="Mixxx visualiser — terminal ASCII or GLSL shader window",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--window", "-w", action="store_true",
                        help="Open a GLSL shader window (default: terminal ASCII)")
    parser.add_argument("--device", default=None,
                        help='Audio input (e.g. "BlackHole 2ch" or 1)')
    parser.add_argument("--list-devices", action="store_true",
                        help="List audio inputs and exit")
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
