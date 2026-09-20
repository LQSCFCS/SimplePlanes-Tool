# SimplePlanes Tool — Unity TMP Rich Text Editor

**English** | [中文](README.zh-CN.md)

![version](https://img.shields.io/badge/version-0.75-blue)
![python](https://img.shields.io/badge/python-3.7%2B-blue)
![pyqt5](https://img.shields.io/badge/PyQt5-5.15%2B-green)

A visual editor for **Unity TextMeshPro** rich text.
Drag characters, bind expressions, preview in real time, export rich text
that pastes straight into Unity. No art assets. No coding.

---

## What is this

Building a HUD in Unity usually means either drawing textures (asset hell)
or hand-writing TMP rich text with FunkyTree expressions (edit hell).

This tool makes the second approach **visual**: place characters on a canvas,
set size / rotation / color by dragging, bind them to flight data or control
variables with expressions like `{Altitude*10}`, `{sin(Time*60)*5}`,
`{clamp(Throttle,0,1)*100}`, preview live, export, paste into SimplePlanes.

---

## Features

### Canvas editing
- Drag / scale / rotate with bounding box handles
- Grid snap, helper snap, line snap
- Multi-select, rubber-band select, batch edit
- Ruler, grid, canvas bounds — all toggleable
- Wheel zoom, middle / `Alt`+LMB pan, Fit View
- Adapts to 4K / 2K / 1080p / 720p , respects system DPI

### Expression engine (FunkyTree style)
- **Built-in vars**: `Throttle` `Yaw` `Brake` `Pitch` `Roll` `Heading` `VTOL` `Trim` `Activate1~8` `LandingGear`
- **Flight data**: `Altitude` `GS` `IAS` `TAS` `Fuel` `AngleOfAttack` `PitchAngle` `RollAngle` `Time` `GForce` `Latitude` `Longitude` …
- **Functions**: `sin` `cos` `clamp` `lerp` `smoothstep` `pingpong` `sqrt` `atan2` … 30+
- **Stateful**: `sum()` (integrate), `rate()` (differentiate), `smooth()` (low-pass), `PID()`
- **Ternary**: `{Throttle>0.5?"ON":"OFF"}`
- **Format suffix**: `{Altitude;0.0}` → 1 decimal place

### Control panel
- Dual joysticks: L (throttle / yaw / brake), R (pitch / roll)
- Attitude joystick + artificial horizon + live pitch / roll readout
- Heading knob, VTOL / Trim sliders
- 8 Activate buttons + LandingGear + Brake
- **Time control**: run test, speed multiplier, reset
- Can **float out** as a separate window, or dock back

### Helper objects
- Point / line / circle
- Bindable expressions (let the helper itself animate)
- Snap to grid / snap to helpers / lock in place

### Binding system
- Attach a char to another char, point, line, or circle
- Three modes:
  - **Static** (keep relative position & angle)
  - **Slide on line** (driven by a control variable)
  - **Orbit on circle** (tangent-aligned optional)
- Parent highlighted with a **purple dashed box**
- Batch bind / unbind / recursive unbind

### Char list panel
- Tree folders, drag to rearrange
- Single / dual column (auto-collapse on switch)
- Hide / show, move up / down, duplicate
- Share as JSON / import from JSON
- `Del` key, right-click menu (rename / hide / delete)

### Custom variables (Variable Outputs)
- User-named variables with min / max / value and a live slider
- Name conflict → red highlight; illegal chars rejected

### Custom functions (CSE compression)
- Auto-extract common sub-expressions, shrink main output
- **Compression level**: Low / Mid / High
- **Variable prefix** customizable (`V`, `abc`, `myVar` …)
- Dead-def elimination, fusion, secondary inlining, renumbering

### Import / Export
- Import Unity TMP rich text, export PNG
- Save / open project as JSON, drag-and-drop to load
- **Save settings**: auto-save everything, restore on next launch
  - Canvas, bindings, helpers
  - Control values, flight data, custom variables
  - Compression level, prefix, panel visibility, display toggles
  - Main window geometry, floating panel / sub-window states

### Language
- Chinese / English, switchable without restart
- **Reversed label**: Chinese UI shows `Language:`, English UI shows `语言:`

---

## Install

### Option 1: prebuilt exe (Windows)

Download `TMPEditor.exe` from the [Releases](https://github.com/LQSCFCS/SimplePlanes-Tool/releases) page, double-click to run.

### Option 2: run from source

```bash
# Python 3.7+
pip install PyQt5
python tmp_editor_0.75.py
```

### Option 3: build your own exe

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name TMPEditor tmp_editor_0.75.py
```

Result lands in `dist/`.

---

## Quick start

1. **Add a char** — toolbar `+ Add Char`, or right-click the canvas → Add Char
2. **Place it** — drag to move, drag a corner to scale, drag the top dot to rotate
3. **Write an expression** — right panel → `Text Content` → `{Altitude;0.0}m`
4. **Animate it** — select the char, right-click → `🔗 Bind to…`, click a parent object
5. **Preview** — tick `Run Test`, or move control panel sticks; canvas updates live
6. **Export** — menu `More → Export Rich Text`, copy & paste into Unity TMP

---

## Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl + C` / `Ctrl + V` | Copy / paste (at cursor, snaps to grid if enabled) |
| `Ctrl + Z` / `Ctrl + Y` | Undo / redo (50 steps) |
| `Ctrl + A` | Select all |
| `Ctrl + D` | Duplicate |
| `Del` / `Backspace` | Delete |
| `← ↑ → ↓` | Nudge (`Shift` accelerates) |
| `Ctrl + =` / `Ctrl + -` | Scale selection |
| `Q` / `E` | Rotate ∓5° |
| `B` | Toggle bounding boxes |
| Mouse wheel | Zoom canvas |
| Middle / `Alt` + LMB | Pan canvas |

---

## Expression cheat sheet

```text
Simple var     {Altitude}
Format suffix  {Altitude;0.0}          → 1 decimal
Math           {Throttle*100}
Function       {sin(Time*60)*5}
Conditional    {Activate1>0?"ARMED":"SAFE"}
Integrate      {sum(Throttle)}         → throttle integrated over time
Differentiate  {rate(Altitude)}        → climb rate
Smooth         {smooth(noise,10)}      → 10 units / s low-pass
PID            {PID(target,current,1,0,0)}
```

Rich text tags (inside a char's text):

```text
<color=#FF0000>red</color>
<alpha=#80>translucent</alpha>
<mark=#FFFF00FF>yellow bg</mark>
<b>bold</b> <i>italic</i> <u>underline</u> <s>strike</s>
<size=150%>big</size>
<rotate=45>rotated</rotate>
<br> line break
<space=4> controlled space
```

---

## FAQ

**Q: Exported rich text exceeds 3072 bytes?**
A: Unity TMP caps a single text block around 3072 bytes. Try:
- bump CSE compression to **High**
- share parent references between chars
- split into multiple text blocks

**Q: Canvas position doesn't match Unity?**
A: Make sure `Canvas W` / `Canvas H` match your Unity setup, and that the TMP component uses the same font & size.

**Q: Some chars render empty?**
A: Expression syntax error. Check the preview line in the property panel; invalid expressions show in red.

**Q: How do I back up my settings?**
A: Menu `More → Save Settings`, pick a JSON path. Every edit auto-writes to that file; next launch auto-restores.

---


## Requirements

- Python 3.7+
- PyQt5