# mixxx-visuals

Real-time music-reactive visualiser for [Mixxx DJ software](https://github.com/mixxxdj/mixxx).

Listens to your audio output, detects beats in real time, and renders animated visuals in a standalone window or terminal. No Mixxx configuration required.

Two rendering modes, toggled with `a` at any time:

- **GLSL shaders** — GPU-accelerated full-screen visuals (default in `--window`)
- **ASCII art** — character-based animations (default in terminal mode)

## Shader modes

| Mode | Description |
|------|-------------|
| **ripple** | Water-surface interference pattern, bass drives amplitude |
| **plasma** | Overlapping sine-wave colour field, mid/high shift the hues |
| **matrix** | Infinite 3D tunnel with falling-character rain aesthetic |
| **fire** | Procedural fbm-noise fire that surges on beat |
| **particles** | Nebula clouds and stars that burst outward on beat |
| **dancer** | Circular spectrum rings — bass/mid/high each pulse a ring |

## ASCII art modes

| Mode | Description |
|------|-------------|
| **ripple** | Concentric rings expanding outward on every beat |
| **plasma** | Demoscene sine-wave plasma — hue and speed drift with BPM |
| **matrix** | Falling character rain, speed and brightness tied to beat |
| **fire** | ASCII fire simulation that surges on beat |
| **particles** | Sparks burst from centre on each beat, fade with gravity |
| **dancer** | Stick figure cycling through 8 dance poses each beat |
| **charm** | 77-frame imported dance animation by Charm Ladonna, speed synced to BPM, colour flashes on beat |

Press `m` to cycle through modes, `a` to toggle between shader and ASCII rendering.

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

**Standalone window — audio loopback** *(beat detection from audio)*
```bash
python main.py --window --device "BlackHole 2ch"
```

**Standalone window — Mixxx MIDI bridge** *(accurate BPM + beat from Mixxx's beat grid)*
```bash
python main.py --window --mixxx
```

**Both — MIDI bridge for BPM/beat + audio for frequency bands**
```bash
python main.py --window --mixxx --device "BlackHole 2ch"
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
--mixxx             Receive BPM + beat data from Mixxx via the MIDI bridge
--midi-port PORT    MIDI input port for the bridge (default: "IAC Driver Bus 1")
--list-devices      List available audio input devices and exit
--list-midi         List available MIDI input ports and exit
```

## Mixxx MIDI bridge setup

The bridge gives the visualiser access to Mixxx's internal beat grid — more accurate than audio-based detection, especially at low volumes or during breakdowns.

### 1. Enable the IAC Driver (macOS virtual MIDI bus)

1. Open **Audio MIDI Setup** (Spotlight → "Audio MIDI Setup")
2. **Window → Show MIDI Studio**
3. Double-click **IAC Driver** → check **"Device is online"**

### 2. Install the controller mapping

Copy both files from the `controller/` folder into Mixxx's controller directory:

```
~/Library/Containers/org.mixxx.mixxx/Data/Library/Application Support/Mixxx/controllers/
```

```bash
cp controller/mixxx-visuals-bridge.* \
  ~/Library/Containers/org.mixxx.mixxx/Data/Library/Application\ Support/Mixxx/controllers/
```

### 3. Enable the mapping in Mixxx

1. **Mixxx → Preferences → Controllers**
2. Select **"Mixxx Visuals Bridge"** from the list
3. Set its **Output port** to **"IAC Driver Bus 1"**
4. Click **Enable** and **Apply**

### 4. Install the Python dependency

```bash
pip install python-rtmidi
```

### 5. Run

```bash
python main.py --window --mixxx
```

Add `--device "BlackHole 2ch"` if you also want bass/mid/high frequency data for the shader modes.

### Controls

| Key | Action |
|-----|--------|
| `a` | Toggle between GLSL shader and ASCII art rendering |
| `m` | Cycle visual mode (within current rendering type) |
| `+` / `-` | Increase / decrease brightness |
| `f` | Toggle fullscreen |
| `t` | Toggle always-on-top *(useful as a second-monitor DJ overlay)* |
| `q` / ESC | Quit |

## Architecture

```
┌─ AudioDataSource  — audio capture + FFT beat detection (optional)  ─┐
│  MixxxMidiSource  — SysEx MIDI bridge → accurate BPM + beat phase   │
└──────────────────────────────────┬───────────────────────────────────┘
                                   ↓
                             MusicState
                    BPM · beat phase · volume · beat count
                                   ↓
                             ShaderWidget  (QOpenGLWidget)
                          ┌────────┴────────┐
                    GLSL shaders        AsciiVisualizer  (press 'a')
                    (moderngl)               ↓
                                       Canvas (abstract)
                                    ├── CursesCanvas  (terminal)
                                    └── QtCanvas      (Qt window)
```

`MixxxMidiSource` and `AudioDataSource` can run simultaneously — MIDI provides BPM/beat, audio provides frequency bands (bass/mid/high) for the shaders.

## Project layout

```
main.py                  entry point
state.py                 shared music state + beat interpolation
sources/
  base.py                DataSource interface
  audio.py               audio capture + FFT beat detection
  beat_detector.py       numpy FFT bass-band energy spike detector
  midi_source.py         Mixxx MIDI bridge receiver
controller/
  mixxx-visuals-bridge.midi.xml   Mixxx controller mapping (install in Mixxx)
  mixxx-visuals-bridge.js         JS script — reads ControlProxy, sends SysEx
visuals/
  canvas.py              Canvas ABC + colour constants
  curses_canvas.py       terminal backend
  qt_window.py           Qt window + QtCanvas + ShaderWidget
  ascii_vis.py           6 ASCII visual modes
  shaders.py             6 GLSL fragment shaders
```
