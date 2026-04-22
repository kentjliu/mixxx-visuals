# mixxx-visuals

Real-time music-reactive ASCII art visualiser for [Mixxx DJ software](https://github.com/mixxxdj/mixxx).

Listens to your audio output, detects beats in real time, and renders animated ASCII art in a standalone window or terminal. No Mixxx configuration required.

![modes: ripple, plasma, matrix, fire, particles, dancer]

## Modes

| Mode | Description |
|------|-------------|
| **ripple** | Concentric rings expanding outward on every beat |
| **plasma** | Demoscene sine-wave plasma — hue and speed drift with BPM |
| **matrix** | Falling character rain, speed and brightness tied to beat |
| **fire** | ASCII fire simulation that surges on beat |
| **particles** | Sparks burst from centre on each beat, fade with gravity |
| **dancer** | Stick figure cycling through 8 dance poses each beat |

Press `m` to cycle through all modes while running.

## Requirements

- Python 3.12+
- [BlackHole 2ch](https://existential.audio/blackhole/) *(free, macOS — for capturing Mixxx audio)*

```bash
pip install -r requirements.txt
```

## Setup

### 1. Install BlackHole

Download and install [BlackHole 2ch](https://existential.audio/blackhole/) — a free virtual audio driver that lets Python read Mixxx's output.

### 2. Create a Multi-Output Device

Open **Audio MIDI Setup** (Spotlight → "Audio MIDI Setup"):

1. Click **+** → **Create Multi-Output Device**
2. Check both **your speakers** and **BlackHole 2ch** as members
3. Set this Multi-Output Device as Mixxx's master output

### 3. Configure Mixxx

**Mixxx → Preferences → Sound Hardware → Master output** → select the Multi-Output Device you just created.

You'll still hear audio through your speakers, and Python will receive a copy via BlackHole.

### 4. Find your device index

```bash
python main.py --list-devices
```

Look for `BlackHole 2ch` in the list.

## Usage

**Standalone window** *(recommended)*
```bash
python main.py --window --device "BlackHole 2ch"
```

**Terminal mode**
```bash
python main.py --device "BlackHole 2ch"
```

**Quick test without BlackHole** *(uses microphone)*
```bash
python main.py --window
```

### Options

```
--window, -w        Open a Qt window instead of running in the terminal
--device DEVICE     Audio input device name or index (e.g. "BlackHole 2ch" or 1)
--list-devices      List available audio input devices and exit
```

### Controls

| Key | Action |
|-----|--------|
| `m` | Cycle visual mode |
| `+` / `-` | Increase / decrease brightness |
| `f` | Toggle fullscreen |
| `t` | Toggle always-on-top *(useful as a second-monitor DJ overlay)* |
| `q` / ESC | Quit |

## Architecture

```
AudioDataSource          — captures audio, detects beats (pure numpy, no aubio)
      ↓
MusicState               — shared state: BPM, beat phase, volume, beat count
      ↓
AsciiVisualizer          — 6 visual modes, backend-agnostic
      ↓
Canvas (abstract)
  ├── CursesCanvas       — terminal mode
  └── QtCanvas           — window mode (renders with QPainter)
```

The `Canvas` abstraction is also the migration path toward embedding directly inside Mixxx as a Qt widget (no other code changes required).

## Project layout

```
main.py                  entry point
state.py                 shared music state + beat interpolation
sources/
  base.py                DataSource interface
  audio.py               audio capture + beat detection
  beat_detector.py       FFT bass-band energy spike detector
visuals/
  canvas.py              Canvas ABC + colour constants
  curses_canvas.py       terminal backend
  qt_window.py           Qt window + QtCanvas backend
  ascii_vis.py           all 6 visual modes
```
