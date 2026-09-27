# SimplePlanes Tool — Unity TMP Rich Text Editor

**English** | [中文](README.zh-CN.md)

![version](https://img.shields.io/badge/version-0.75-blue)
![python](https://img.shields.io/badge/python-3.7%2B-blue)
![pyqt5](https://img.shields.io/badge/PyQt5-5.15%2B-green)

A visual editor for **Unity TextMeshPro** rich text.
Drag characters, bind expressions, preview in real time, export rich text
that pastes straight into SimplePlanes. No art assets. No coding.

![Editor screenshot](https://s1.imagehub.cc/images/2026/09/27/ac6c87fd578ecb506639776283fc9f6e.md.png)

---

## What is this

SimplePlanes' Label part uses Unity TMP (TextMeshPro) rich text. To change a character's size, color, position, or rotation — or to display throttle, speed, or altitude in real time — you have to hand-write a string in the Label, then add expressions, variables, conditionals, and animation functions on top. It quickly turns into an unreadable soup of characters.

**This tool makes all of that visual.**

Drag, scale, and rotate characters on the canvas and see the result live, while the output panel below generates TMP rich text you can paste straight into a SimplePlanes Label part.

---

## Features

- **Visual editing** — Drag, scale, rotate with bounding-box handles; grid / helper snapping; multi-select, rubber-band select, batch edit
- **Full style control** — `pos` / `voffset` / `size` / `rotate` / `color`, all adjustable visually; ruler, grid, canvas bounds toggleable
- **Expression engine (FunkyTree style)** — Built-in control vars (`Throttle` `Yaw` `Pitch` `Roll` `Heading` `VTOL` `Trim` `Activate1~8` `LandingGear`), full flight data, 30+ math functions, stateful functions (`sum()` `rate()` `smooth()` `PID()`), ternary, and format suffix (`{Altitude;0.0}`)
- **Control panel** — Dual joysticks, attitude joystick + artificial horizon, heading knob, VTOL / Trim sliders, 8 Activate buttons, time control; can float out as a separate window
- **Helpers & binding** — Create points / lines / circles; attach a char to any object with static, slide-on-line, or orbit-on-circle modes; parent highlighted with a purple dashed box; batch and recursive unbind
- **Char list panel** — Tree folders, drag to rearrange, single / dual column, hide / show, share as JSON
- **Custom variables** — User-named variables with min / max / value and live slider; name conflicts flagged in red
- **Expression compression (CSE)** — Auto-extract common sub-expressions; Low / Mid / High; custom variable prefix
- **Import / Export** — Import TMP rich text, export PNG, save / open project as JSON, auto-save settings and restore on next launch
- **Bilingual UI** — Chinese / English, switchable without restart

---

## Runtime Environment

- Language: Python 3.7+
- UI: PyQt5
- Dependency: `pip install PyQt5`
- Run: Just run the script — no compilation needed
- Platform: Windows / macOS / Linux

---

## Usage Notes

**Canvas**: Scroll wheel to zoom | Middle mouse or Alt+LMB to pan | LMB to select, drag to move | RMB for menu, RMB drag to box-select | Double-click to edit text | Delete to remove | Ctrl+Z/Y to undo/redo | Ctrl+C/V to copy/paste | Arrow keys to nudge | Q/E to rotate

**Features**: Supports FunkyTree expressions, flight data, helper snapping, custom variables, expression compression, project save & auto-restore, Chinese/English switching, and more

**⚠️⚠️⚠️ The single most important thing**:
When pasting the output into a Label part in-game, **you must first click the small pencil icon ![pencil icon](https://s1.imagehub.cc/images/2026/09/27/598e71c05746174ae47fce1f17220d8f.png) next to the text input box to fully expand it before pasting**. Otherwise the game will try to reflow a very long text while the box is collapsed, causing severe lag — or even a white screen and crash.

---

## Install

**Option 1 — prebuilt exe (Windows)**: Download `TMPEditor.exe` from the [Releases](https://github.com/LQSCFCS/SimplePlanes-Tool/releases) page and double-click to run.

**Option 2 — run from source**:

```bash
pip install PyQt5
python tmp_editor_0.75.py
