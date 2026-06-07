# 👁️ Eye Health Desktop Agent

![image alt](https://github.com/Manjunatha-kv01/Eye-Health-Desktop-Agent/blob/136454b59c59dd4dd0a7c69c536f437dae4ef645/WhatsApp%20Image%202026-06-07%20at%2017.17.17.jpeg)


> An open-source desktop agent that runs silently in the background and actively protects your eyes while you work — powered by Python, OpenCV, MediaPipe, and PyQt6.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)
![PyQt6](https://img.shields.io/badge/UI-PyQt6-41cd52?logo=qt)
![MediaPipe](https://img.shields.io/badge/AI-MediaPipe-ff6f00?logo=google)
![OpenCV](https://img.shields.io/badge/Vision-OpenCV-5c3ee8)
![License](https://img.shields.io/badge/License-MIT-green)
![Privacy](https://img.shields.io/badge/Privacy-100%25%20Local-brightgreen)

---

## What It Does

Most eye-health apps tell you to take breaks. This one watches you work and acts — blinking too little, sitting too close, slouching forward, working in a dark room — it catches all of it in real time, adjusts your screen brightness automatically based on your pupil dilation, and shows you a live health dashboard so you always know exactly how your eyes are doing.

---

## Feature Overview

| Feature | How It Works |
|---|---|
| **Blink Monitoring** | Eye Aspect Ratio (EAR) algorithm on MediaPipe FaceMesh landmarks. Alerts when blink rate drops below 8/min. |
| **Screen Distance Detection** | Pinhole camera model using inter-cheek face width. Warns if you're closer than 50 cm. |
| **Posture Detection** | Tracks nose-tip Y position relative to ideal. Fires posture alert on forward-head lean. |
| **20-20-20 Break System** | Every 20 min: floating overlay counts down 20 s while you look 20 ft away. Long break every 60 min. |
| **Ambient Light Detection** | Webcam luminance + screen brightness API. Recommends adjustments for dim or bright rooms. |
| **Pupillometry (Auto-Brightness)** | Measures iris diameter from 10 refined iris landmarks. Normalises by face width. EMA-smoothed. Automatically adjusts screen brightness based on pupil dilation. |
| **Gaze Zone Tracking** | Detects whether you're looking at the top, centre, or bottom of the screen. |
| **Circadian Protection** | Reduces blue light at 6 PM (macOS Night Shift / Linux redshift). Full night mode at 9 PM. |
| **Eye Strain Score** | Weighted 0–100 score from 5 factors every 60 seconds. Saved to local SQLite DB. |
| **Health Dashboard** | Dark-mode PyQt6 window with live feed, metric cards, weekly bar chart, brightness sparkline. |
| **System Tray** | Persistent tray icon — open dashboard, pause/resume monitoring, quit. |
| **Local-Only Privacy** | Zero cloud. Webcam frames never leave your machine. All data stored in a local SQLite file. |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Your Laptop Webcam                    │
└────────────────────────┬────────────────────────────────┘
                         │ raw frames (30 fps)
                         ▼
┌─────────────────────────────────────────────────────────┐
│              AI Vision Engine  (core/)                   │
│                                                          │
│  OpenCV  ──►  MediaPipe FaceMesh (468 + 10 iris pts)    │
│                                                          │
│  ├── EAR Blink Detector          ──► blink_rate         │
│  ├── Pinhole Distance Estimator  ──► distance_cm        │
│  ├── Head-Pose Posture Analyser  ──► posture_alert      │
│  └── Pupillometry Engine ────────► pupil_ratio          │
│       ├── Iris diameter (px)          brightness_hint   │
│       ├── EMA smoothing               gaze_zone         │
│       └── 60-frame calibration                          │
└────────────────────────┬────────────────────────────────┘
                         │ VisionState (shared, thread-safe)
                         ▼
┌─────────────────────────────────────────────────────────┐
│               Eye Health Engine  (engine/)               │
│                                                          │
│  ├── Break Manager    20-20-20 + long-break scheduling  │
│  ├── Scoring Engine   weighted 0-100 eye strain score   │
│  ├── Brightness Ctrl  pupil → screen brightness (sbc)   │
│  ├── Circadian Mgr    blue-light reduction by time      │
│  └── Notification Mgr desktop alerts (plyer)            │
└────────────────┬───────────────────┬────────────────────┘
                 │                   │
    ┌────────────▼──────┐   ┌────────▼───────────────────┐
    │   System Tray     │   │   PyQt6 Dashboard           │
    │   (pystray)       │   │                             │
    │                   │   │  Live feed + HUD overlay    │
    │  Open Dashboard   │   │  Blink / Distance / Posture │
    │  Pause / Resume   │   │  Pupil ratio + gaze zone    │
    │  Quit             │   │  Auto-brightness sparkline  │
    └───────────────────┘   │  Weekly score bar chart     │
                            │  Today's summary cards      │
                            └─────────────────────────────┘
                                         │
                            ┌────────────▼────────────────┐
                            │   SQLite Database (local)    │
                            │   sessions / scores /        │
                            │   notifications / posture    │
                            └─────────────────────────────┘
```

---

## Project Structure

```
eye-health-agent/
│
├── main.py                        # Entry point — wires all threads + Qt app
├── config.yaml                    # All tuneable settings
├── requirements.txt
│
├── core/                          # Vision & sensing layer
│   ├── vision_engine.py           # Webcam thread → EAR, distance, posture, iris
│   ├── pupillometry.py            # Iris landmark → pupil ratio, EMA, gaze zone
│   └── ambient_light.py           # Room brightness estimation
│
├── engine/                        # Health logic layer
│   ├── eye_health_engine.py       # Central coordinator (1-second tick loop)
│   ├── break_manager.py           # 20-20-20 rule + long-break scheduler
│   ├── scoring.py                 # Eye strain score calculator (0-100)
│   ├── brightness_controller.py   # Pupil-driven auto screen brightness
│   └── circadian.py               # Evening / night blue-light management
│
├── agent/                         # OS integration layer
│   ├── notification_manager.py    # Cross-platform notifications (plyer)
│   └── tray_agent.py              # System tray icon (pystray)
│
├── dashboard/                     # PyQt6 UI layer
│   ├── main_window.py             # Main dark-mode dashboard window
│   └── break_overlay.py           # Floating 20-second countdown overlay
│
├── utils/                         # Shared utilities
│   ├── config.py                  # YAML loader with dot-access
│   ├── database.py                # SQLAlchemy ORM (SQLite)
│   └── logger.py                  # Rotating file + console logger
│
├── assets/icons/
│   └── generate_icons.py          # Script to generate PNG tray icons
│
├── tests/
│   ├── test_scoring.py            # Unit tests for scoring engine
│   └── test_break_manager.py      # Unit tests for break manager
│
├── data/                          # Auto-created — SQLite database lives here
└── logs/                          # Auto-created — rotating log files live here
```

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.10 + | 3.12 recommended |
| Webcam | Any USB or built-in | 720p+ for best pupillometry |
| macOS / Linux / Windows | — | All three supported |
| `redshift` (Linux only) | Any | Optional, for blue-light control |

---

## Step-by-Step Installation

### Step 1 — Clone the repository

```bash
git clone https://github.com/Manjunatha-kv01/eye-health-agent.git
cd eye-health-agent
```

### Step 2 — Create a Python virtual environment

```bash
python3 -m venv venv
```

This creates an isolated environment so the project's dependencies don't conflict with anything else on your system.

### Step 3 — Activate the virtual environment

**macOS / Linux:**
```bash
source venv/bin/activate
```

**Windows:**
```bash
venv\Scripts\activate
```

You should see `(venv)` in your terminal prompt.

> **macOS note:** If `python3` still resolves to system Python after activating, use `venv/bin/python3` explicitly for all commands in this guide.

### Step 4 — Install dependencies

```bash
pip install -r requirements.txt
```

This installs:

| Package | Purpose |
|---|---|
| `opencv-python` | Webcam capture and frame processing |
| `mediapipe` | FaceMesh AI model — 468 facial + 10 iris landmarks |
| `numpy` | Numerical computations (EAR, distances) |
| `PyQt6` | Desktop GUI framework (dashboard + overlay) |
| `plyer` | Cross-platform desktop notifications |
| `pystray` | System tray icon |
| `Pillow` | Image handling for tray icons |
| `SQLAlchemy` | ORM for SQLite session/score storage |
| `screen-brightness-control` | Read and set display brightness |
| `PyYAML` | Parse `config.yaml` |
| `scipy` | Statistical utilities |
| `schedule` | Job scheduling utilities |
| `psutil` | System information |

### Step 5 — Generate tray icons

```bash
python3 assets/icons/generate_icons.py
```

This creates the PNG icon set used by the system tray and notifications. Only needs to be run once.

### Step 6 — (Optional) Calibrate your camera focal length

Open `config.yaml` and adjust:

```yaml
distance:
  focal_length_px: 500      # increase if distances read too low, decrease if too high
  avg_face_width_cm: 14.0   # average human face width — leave as-is
```

To find your camera's focal length precisely: sit exactly 60 cm from your screen, run the app, check the "Screen Distance" card. If it shows a value far from 60, tune `focal_length_px` until it matches.

### Step 7 — Run the app

```bash
# If venv is activated:
python3 main.py

# Or using the venv Python directly (always works):
venv/bin/python3 main.py
```

The dashboard opens immediately. A tray icon appears in your menu bar / system tray.

---

## First Launch Walkthrough

```
[00:00]  App starts — vision engine opens webcam
[00:02]  MediaPipe detects your face
[00:03]  Pupillometry begins collecting 60 calibration frames
[~00:05] Calibration complete — baseline pupil ratio established
         Auto-brightness is now active

[20:00]  "⏱ 20-20-20 Rule: Look 20 feet away for 20 seconds!"
         → Floating overlay appears with a countdown timer

[35:00]  "📏 You're 43 cm from the screen — move back to at least 40 cm."
         → You slouch forward while reading docs

[60:00]  "🛑 Time for a 5-minute break — stand up and stretch!"
         → Long break notification fires

[18:00]  Evening mode activates
         → Blue light reduced by 30% automatically via Night Shift / redshift
```

---

## Dashboard Guide

### Left Panel

| Section | What you see |
|---|---|
| **Live Feed** | Annotated webcam feed with cyan iris circles, EAR value, blink count, distance estimate, posture alert overlay, brightness hint badge, and gaze zone label |
| **Live Metrics** | 4 cards: Blink Rate · Screen Distance · Posture status · EAR value — all colour-coded green / amber / red |

### Right Panel

| Section | What you see |
|---|---|
| **Today's Summary** | Screen time · Blinks today · Breaks taken · Eye score |
| **Eye Strain Risk** | Low / Medium / High with colour-coded progress bar |
| **👁 Pupillometry & Auto-Brightness** | Pupil ratio · Iris diameter · Gaze zone · Screen brightness · Calibration bar · Hint badge · Auto/manual toggle · Brightness slider · Brightness history sparkline |
| **Weekly Eye Scores** | 7-day bar chart, bars coloured by risk level |
| **Recent Alerts** | Last 6 notification messages with timestamps |

---

## Pupillometry & Auto-Brightness — How It Works

This is the novel feature of this project. Most commercial solutions (Tobii, Apple, Samsung) use dedicated hardware. This uses your existing webcam.

### The algorithm

```
1. MediaPipe detects 10 refined iris landmarks per eye
   Left iris:  landmarks 468–472
   Right iris: landmarks 473–477

2. Iris diameter measured each frame:
   horizontal_span = distance(right_boundary, left_boundary)
   vertical_span   = distance(top_boundary, bottom_boundary)
   diameter        = (horizontal_span + vertical_span) / 2

3. Normalise by face width (removes distance-from-camera effect):
   pupil_ratio = iris_diameter_px / inter_cheek_width_px

4. EMA smoothing (α = 0.15) removes blink noise:
   ema = 0.15 × ratio + 0.85 × previous_ema

5. 60-frame baseline calibration on startup

6. Brightness decision:
   ratio > 0.115  →  INCREASE  (pupils dilated = dim room)
   ratio < 0.080  →  DECREASE  (pupils constricted = bright room)
   otherwise      →  HOLD

7. Apply via screen_brightness_control, throttled to every 8 seconds
   Step size scaled by deviation magnitude (1–3× base step of 5%)
   Hard clamp: [10%, 100%]
```

### Why this works

Pupils dilate in dim environments (the eye opens up to gather more light). When your room gets darker, your pupils get larger. The system detects this and raises screen brightness so your screen stays comfortable relative to the environment — without you doing anything.

### Live indicators on the feed

The annotated camera view shows:
- **Cyan circles** drawn on each iris in real time
- `Pupil:0.0971` — current smoothed ratio (bottom-left of frame)
- `Bright hint: HOLD` — current action in colour (green=increase, blue=decrease, grey=hold)
- `Gaze: Centre` — current vertical gaze zone

---

## Eye Strain Score Formula

The score is computed every 60 seconds and saved to the database:

```
Score = (blink_rate   × 0.25)
      + (session_len  × 0.20)
      + (distance     × 0.20)
      + (break_comply × 0.20)
      + (ambient_lux  × 0.15)
```

Each sub-score is 0–100 before weighting:

| Factor | 100 (best) | 0 (worst) |
|---|---|---|
| Blink rate | ≥ 15 blinks/min | ≤ 5 blinks/min |
| Session length | ≤ 20 min | ≥ 90 min |
| Screen distance | ≥ 60 cm | ≤ 40 cm |
| Break compliance | 100% taken | 0% taken |
| Ambient light | ~300 lux | < 50 or > 500 lux |

| Overall score | Risk level |
|---|---|
| 70 – 100 | 🟢 Low |
| 45 – 69 | 🟡 Medium |
| 0 – 44 | 🔴 High |

---

## Configuration Reference

All settings live in `config.yaml`. Changes take effect on next launch.

### Camera

```yaml
camera:
  device_index: 0          # 0 = default webcam, 1 = second camera
  resolution_width: 640
  resolution_height: 480
  fps: 30
```

### Blink detection

```yaml
blink:
  low_rate_threshold: 8    # alert if blink rate drops below this (blinks/min)
  ear_threshold: 0.21      # EAR value below which eye is counted as closed
  ear_consecutive_frames: 3 # frames eye must stay closed to register a blink
```

### Screen distance

```yaml
distance:
  warning_cm: 50           # warn when closer than this
  focal_length_px: 500     # tune to match your webcam
```

### Breaks

```yaml
breaks:
  work_interval_minutes: 20     # 20-20-20 interval
  long_break_interval_minutes: 60
  mandatory_lock: false         # set true to lock screen during long breaks
```

### Pupillometry & auto-brightness

```yaml
pupillometry:
  enabled: true
  calibration_frames: 60        # how many frames to build baseline
  smoothing_alpha: 0.15         # EMA factor — lower = smoother but slower
  dilation_high: 0.115          # ratio above this → raise brightness
  dilation_low: 0.080           # ratio below this → lower brightness
  brightness_min: 10            # never go below 10%
  brightness_max: 100
  brightness_step: 5            # max % per adjustment
  adjust_interval_seconds: 8    # throttle — minimum gap between changes
```

### Circadian / blue light

```yaml
circadian:
  evening_start_hour: 18        # start reducing blue light at 6 PM
  night_start_hour: 21          # full night mode at 9 PM
  blue_light_reduction_evening: 30   # % reduction
  blue_light_reduction_night: 60
```

### Notifications

```yaml
notifications:
  enabled: true
  min_interval_seconds: 300     # no repeat within 5 minutes for same category
```

---

## Running Tests

```bash
# Make sure venv is active
venv/bin/python3 -m pytest tests/ -v
```

Expected output:

```
tests/test_scoring.py::test_perfect   PASSED
tests/test_scoring.py::test_bad       PASSED
tests/test_scoring.py::test_clamped   PASSED
tests/test_scoring.py::test_fields    PASSED
```

No camera or display required — tests only cover pure-logic modules.

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'yaml'`

Your terminal's `python3` is the system Python, not the venv. Always run:
```bash
venv/bin/python3 main.py
```
Or ensure the venv is properly activated with `source venv/bin/activate` before running.

### Camera not opening

- Make sure no other app (Zoom, Teams, FaceTime) is using the camera
- Try changing `camera.device_index` to `1` or `2` in `config.yaml`
- On macOS, grant Terminal/iTerm camera permission in System Settings → Privacy → Camera

### Distance reading is wrong

Tune `distance.focal_length_px` in `config.yaml`:
- If the app shows you're 40 cm away when you're actually 60 cm — increase the value
- If it shows 80 cm when you're 60 cm — decrease the value

### Brightness not changing (macOS)

On macOS, screen brightness control via software requires the `screen-brightness-control` library to have accessibility/display permissions. If auto-brightness silently fails, the app still works — just the brightness adjustment is skipped. The pupil ratio and hint badge still work correctly.

### Posture alert firing constantly

Your webcam angle may be above or below eye level. Adjust `distance.forward_head_threshold` in `config.yaml`:
```yaml
distance:
  forward_head_threshold: 0.20   # increase to make it less sensitive
```

### Blue light / Night Shift not working (macOS)

The Night Shift AppleScript bridge may need System Settings → Privacy & Security → Automation to allow Terminal to control System Events. Alternatively, enable Night Shift manually in Display settings.

---

## Privacy

- **All processing is 100% local.** No frame, image, or health data ever leaves your machine.
- The webcam is only accessed while the app is running and not paused.
- Health data (sessions, scores, alerts) is stored in `data/eye_health.db` — a plain SQLite file on your own disk. You can delete it at any time.
- No accounts, no telemetry, no network requests.

---

## How It Was Built — Technical Decisions

| Decision | Why |
|---|---|
| **MediaPipe FaceMesh** over dlib | 468 landmarks + refined iris, runs at 30 fps on CPU, no GPU needed |
| **EAR for blink detection** | Proven algorithm — simple ratio of vertical/horizontal eye distances |
| **Pinhole camera model for distance** | Accurate enough for face-to-screen estimation without calibration hardware |
| **EMA smoothing for pupillometry** | Removes blink-induced spikes without introducing processing lag |
| **SQLite over cloud DB** | Zero dependencies, zero privacy risk, zero cost |
| **PyQt6 for UI** | Native rendering on all three platforms, full widget control |
| **Threaded architecture** | Vision engine, health engine, ambient monitor, tray agent all run independently so the UI stays responsive |

---

## Roadmap

- [ ] Predict eye fatigue 15 minutes in advance (LSTM on session history)
- [ ] Personalised work-rest schedule recommendations (ML)
- [ ] Dry-eye risk score from blink pattern variance
- [ ] Workstation improvement suggestions (distance + lighting ML model)
- [ ] Voice alerts option
- [ ] Multi-monitor brightness support
- [ ] Mobile companion app (push break reminders when away from desk)
- [ ] Export health report as PDF

---

## Contributing

Pull requests are welcome. For major changes, open an issue first to discuss what you'd like to change.

```bash
# Fork, clone, create branch
git checkout -b feature/your-feature-name

# Make changes, run tests
venv/bin/python3 -m pytest tests/ -v

# Commit and push
git commit -m "feat: describe your change"
git push origin feature/your-feature-name
```

---

## License

MIT — free to use, modify, and distribute.

---

*Built for developers, students, office workers, and gamers who spend long hours in front of a screen.*
*The "GitHub Copilot for Eye Health."*
