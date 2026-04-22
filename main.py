"""
Mixxx ASCII Visualiser

Driven by live audio capture + real-time beat detection (aubio).
No Mixxx configuration required.

Quick start:
  pip install -r requirements.txt
  python main.py --list-devices   # find your audio input
  python main.py                  # use default mic (quick test)
  python main.py --device "BlackHole 2ch"   # capture Mixxx output

macOS loopback setup (to capture Mixxx audio):
  1. Install BlackHole: https://existential.audio/blackhole/
  2. Open Audio MIDI Setup → create a Multi-Output Device
       members: your speakers + BlackHole 2ch
  3. Mixxx → Preferences → Sound Hardware → Master → BlackHole (or the Multi-Output)
  4. python main.py --device "BlackHole 2ch"
"""

import argparse
import curses
import logging

from state import MusicState
from sources.audio import AudioDataSource, list_devices
from visuals.ascii_vis import AsciiVisualizer


def _run(stdscr, args: argparse.Namespace) -> None:
    state = MusicState()
    source = AudioDataSource(device=args.device)
    source.start(state)
    vis = AsciiVisualizer(stdscr, state)
    try:
        vis.run()
    finally:
        source.stop()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mixxx ASCII visualiser — audio-driven",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--device",
        default=None,
        help='Audio input device name or index (e.g. "BlackHole 2ch" or 3)',
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List available audio input devices and exit",
    )
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    if args.list_devices:
        list_devices()
        return

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    try:
        curses.wrapper(lambda stdscr: _run(stdscr, args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
