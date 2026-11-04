# 🎨 Touchpad Drawing Pad (`touchpad-tablet`)

> Turn your Linux laptop's built-in touchpad into an absolute-position graphics tablet (digitizer) for **Krita**, **GIMP**, **Blender**, **Inkscape**, and **Xournal++**.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](pyproject.toml)
[![Platform: Linux](https://img.shields.io/badge/Platform-Linux-orange.svg)](pyproject.toml)

---

## 💡 How It Works

A common misconception is that laptop touchpads are "relative mice". At the hardware and kernel driver levels, **every capacitive touchpad is an absolute coordinate digitizer**. The sensor continuously tracks exact $(X, Y)$ coordinate matrices.

Relative cursor motion on desktop Linux is an artificial software abstraction synthesized by `libinput`.

`touchpad-tablet` works by:
1. **Direct Evdev Capture:** Reading the raw multi-touch stream (`ABS_MT_POSITION_X`, `ABS_MT_POSITION_Y`) directly from `/dev/input/event*`.
2. **Cursor Suppression (`EVIOCGRAB`):** Taking an exclusive kernel grab on the touchpad so the desktop mouse cursor remains completely frozen while you draw.
3. **Virtual Tablet Synthesis (`/dev/uinput`):** Creating a virtual Wacom-compatible graphics tablet (`BUS_USB`, `BTN_TOOL_PEN`, `BTN_TOUCH`, `ABS_X`, `ABS_Y`, `ABS_PRESSURE`).
4. **Compositor & App Integration:** Wayland (Hyprland, Sway, GNOME, KDE) and X11 immediately recognize the virtual tablet via the `zwp_tablet_manager_v2` / XInput protocol. Creative applications automatically treat your touchpad like an external drawing tablet!

For detailed kernel documentation and empirical hardware measurements, see the [In-Depth Research Report](RESEARCH_TOUCHPAD_DRAWING_PAD.md).

---

## ✨ Features

* **Zero External Dependencies:** Built entirely with Python's standard library (`ctypes`, `fcntl`, `struct`, `os`, `socket`). No heavy compilers or third-party packages required.
* **Instant Mode Toggling:** Switch seamlessly between normal mouse touchpad mode and drawing tablet mode with a single CLI command (`touchpad-tablet toggle`), socket IPC, or `SIGUSR1`.
* **Adaptive Jitter Reduction (1€ Filter):** Employs the Casiez et al. **One-Euro adaptive low-pass filter** to eliminate micro-jitter and hand tremor when drawing slow, precise details, while maintaining zero latency during rapid flick strokes.
* **Velocity-Based Pseudo-Pressure:** Laptop capacitive pads lack physical pen pressure springs; `touchpad-tablet` calculates stroke velocity dynamics ($v = \Delta d / \Delta t$) so swift strokes taper smoothly while slow strokes yield bolder, firmer lines.
* **Aspect Ratio Preservation:** Automatically detects your display resolution (via Hyprland / wlroots / xrandr) and corrects geometric distortion so circles drawn on the pad render as true circles on screen (`fit` pillarboxing or `stretch` mode).
* **Clickpad Stylus Actions:** Pressing down on a physical clickpad triggers `BTN_STYLUS` (bringing up Krita's pop-up color palette / brush selector or right-click tools).
* **Desktop Notifications:** Dispatches visual notifications via `notify-send` when tablet mode is enabled or disabled.
* **Systemd User Service Integration:** Easily manage the daemon as a background user service.

---

## 🚀 Quick Start

### 1. Requirements

* Linux Kernel 5.x / 6.x+
* Python 3.10+
* Your user must have permission to read `/dev/input/event*` and `/dev/uinput` (on Arch, Fedora, Debian, and Ubuntu, this simply means being in the `input` group):
  ```bash
  sudo usermod -aG input $USER
  ```
  *(Log out and back in for group changes to take effect).*

### 2. Installation

Clone and install into your environment:

```bash
git clone https://github.com/timsurrealedu/touchpad-drawing-pad.git
cd touchpad-drawing-pad
pip install .
```

Or run directly without installation:

```bash
python3 -m touchpad_tablet devices
```

---

## 🛠️ Usage

### Command-Line Interface

```bash
# 1. Discover detected touchpads and screen resolution
touchpad-tablet devices

# 2. Run the daemon in foreground (test mode)
touchpad-tablet run

# 3. Start daemon in background
touchpad-tablet start

# 4. Check status
touchpad-tablet status

# 5. Toggle between Tablet Mode (drawing) and Mouse Mode (cursor)
touchpad-tablet toggle

# 6. Explicitly enable or disable
touchpad-tablet enable
touchpad-tablet disable

# 7. Stop the daemon
touchpad-tablet stop
```

---

## ⌨️ Window Manager Keybinding Integration

Bind a hotkey in your window manager to quickly toggle between drawing tablet and normal mouse!

### Hyprland (`~/.config/hypr/hyprland.conf`)
```ini
bind = $mainMod, F10, exec, touchpad-tablet toggle
```

### Sway / i3 (`~/.config/sway/config` or `~/.config/i3/config`)
```i3config
bindsym $mod+F10 exec touchpad-tablet toggle
```

### KDE Plasma / GNOME
Create a custom shortcut in **Settings → Keyboard Shortcuts**:
- **Command:** `touchpad-tablet toggle`
- **Shortcut:** `Super + F10` (or your preferred key)

---

## ⚙️ Configuration

Generate a default configuration file at `~/.config/touchpad-tablet/config.toml`:

```bash
touchpad-tablet config --init
```

Example `config.toml`:

```toml
[tablet]
# Specific touchpad node (leave commented to auto-detect)
# device = "/dev/input/event9"

# Startup mode ("tablet" or "mouse")
start_mode = "tablet"

# Aspect ratio mode ("fit" = maintain 16:10 / 16:9 ratio, "stretch" = 1:1 pad stretch)
aspect_ratio = "fit"

# Coordinate smoothing factor (0.0 = raw, 0.35 = balanced, 0.8 = heavy smoothing)
smoothing = 0.35

# Use One-Euro adaptive filter (recommended)
use_one_euro = true

# Pseudo-pressure dynamics
pressure_min = 800
pressure_max = 4096
pressure_curve = "velocity"

# Physical clickpad action ("stylus" = trigger BTN_STYLUS for palette/right-click)
click_action = "stylus"

# Desktop notifications
notifications = true
```

---

## 🖥️ Systemd Background Service

To have the daemon run automatically on login:

```bash
touchpad-tablet install-service
systemctl --user daemon-reload
systemctl --user enable --now touchpad-tablet.service
```

The service starts in `mouse` mode by default, ready to be activated anytime with `touchpad-tablet toggle` or your hotkey!

---

## 🧪 Testing

Run the included test suite with standard Python `unittest`:

```bash
python3 -m unittest discover -s tests -v
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
