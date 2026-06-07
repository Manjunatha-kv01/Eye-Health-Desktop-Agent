"""
Pupillometry Engine

Measures pupil dilation using MediaPipe FaceMesh refined iris landmarks.
Estimates gaze zone (top / centre / bottom of screen).

How it works
------------
MediaPipe's refined FaceMesh model adds 10 iris landmarks:
  Left iris  : 468, 469, 470, 471, 472
  Right iris : 473, 474, 475, 476, 477

Each iris cluster has a centre point (468 / 473) surrounded by 4 boundary
points.  The diameter is computed as the mean of the horizontal and vertical
distances across those boundary points.

Because raw pixel diameter changes with head distance, we normalise it
against inter-cheek face width — producing a stable *pupil ratio* that
reflects dilation independent of how far the user sits from the camera.

The ratio is then smoothed with an Exponential Moving Average (EMA) to
suppress blink-induced noise and micro-movements.

Gaze zone is estimated from the vertical position of the iris centre
landmark relative to the eye bounding box — up / centre / down.
"""
from __future__ import annotations

import collections
from dataclasses import dataclass, field

from utils.config import get_config
from utils.logger import setup_logger

log = setup_logger("pupillometry")

# MediaPipe FaceMesh iris indices (refined model)
_LEFT_IRIS  = [468, 469, 470, 471, 472]   # centre, right, top, left, bottom
_RIGHT_IRIS = [473, 474, 475, 476, 477]

# Face width landmarks (same as VisionEngine)
_LEFT_CHEEK  = 234
_RIGHT_CHEEK = 454

# Eye corners for gaze-zone reference
_LEFT_EYE_INNER  = 133   # inner corner of left eye
_LEFT_EYE_OUTER  = 33    # outer corner
_LEFT_EYE_TOP    = 159
_LEFT_EYE_BOTTOM = 145
_RIGHT_EYE_INNER = 362
_RIGHT_EYE_OUTER = 263
_RIGHT_EYE_TOP   = 386
_RIGHT_EYE_BOTTOM = 374


@dataclass
class PupilData:
    """Result produced each frame by PupillometryEngine.process()."""
    left_diameter_px:  float = 0.0
    right_diameter_px: float = 0.0
    avg_diameter_px:   float = 0.0
    pupil_ratio:       float = 0.0   # normalised by face width
    smoothed_ratio:    float = 0.0   # EMA-smoothed ratio
    gaze_zone:         str   = "Centre"  # Top | Centre | Bottom
    gaze_x:            float = 0.5   # normalised 0-1 horizontal gaze
    gaze_y:            float = 0.5   # normalised 0-1 vertical gaze
    is_calibrated:     bool  = False
    baseline_ratio:    float = 0.0
    relative_dilation: float = 0.0   # smoothed_ratio - baseline (+ = dilated)
    brightness_hint:   str   = "HOLD" # INCREASE | DECREASE | HOLD


class PupillometryEngine:
    """
    Stateful per-session pupillometry analyser.
    Call `process(landmarks, frame_w, frame_h)` every frame.
    Returns a PupilData instance.
    """

    def __init__(self) -> None:
        cfg = get_config()
        self._cfg = cfg.pupillometry

        self._alpha        = float(self._cfg["smoothing_alpha"])
        self._calib_needed = int(self._cfg["calibration_frames"])
        self._dil_high     = float(self._cfg["dilation_high"])
        self._dil_low      = float(self._cfg["dilation_low"])
        gz = self._cfg["gaze_zones"]
        self._gz_top       = float(gz["top_threshold"])
        self._gz_bot       = float(gz["bottom_threshold"])

        # Calibration buffer
        self._calib_buf: collections.deque[float] = collections.deque(
            maxlen=self._calib_needed
        )
        self._baseline: float | None = None

        # EMA state
        self._ema: float | None = None

        log.info(
            "PupillometryEngine init — calib_frames=%d  alpha=%.2f  "
            "dil_high=%.3f  dil_low=%.3f",
            self._calib_needed, self._alpha, self._dil_high, self._dil_low,
        )

    # ------------------------------------------------------------------
    # Main API
    # ------------------------------------------------------------------

    def process(self, landmarks, frame_w: int, frame_h: int) -> PupilData:
        """
        Compute pupil metrics from a single frame's face landmarks.

        Parameters
        ----------
        landmarks : mediapipe NormalizedLandmarkList.landmark sequence
        frame_w, frame_h : frame dimensions in pixels
        """
        data = PupilData()

        # ---- iris diameters ----
        l_diam = self._iris_diameter(landmarks, _LEFT_IRIS,  frame_w, frame_h)
        r_diam = self._iris_diameter(landmarks, _RIGHT_IRIS, frame_w, frame_h)
        avg    = (l_diam + r_diam) / 2.0

        data.left_diameter_px  = round(l_diam, 2)
        data.right_diameter_px = round(r_diam, 2)
        data.avg_diameter_px   = round(avg,    2)

        # ---- normalise by face width ----
        lx = landmarks[_LEFT_CHEEK].x  * frame_w
        rx = landmarks[_RIGHT_CHEEK].x * frame_w
        face_w = abs(rx - lx)
        ratio  = (avg / face_w) if face_w > 0 else 0.0
        data.pupil_ratio = round(ratio, 4)

        # ---- EMA smoothing ----
        if self._ema is None:
            self._ema = ratio
        else:
            self._ema = self._alpha * ratio + (1.0 - self._alpha) * self._ema
        data.smoothed_ratio = round(self._ema, 4)

        # ---- calibration ----
        self._calib_buf.append(self._ema)
        if self._baseline is None and len(self._calib_buf) >= self._calib_needed:
            self._baseline = sum(self._calib_buf) / len(self._calib_buf)
            log.info("Pupillometry calibrated — baseline ratio=%.4f", self._baseline)

        data.is_calibrated  = self._baseline is not None
        data.baseline_ratio = round(self._baseline or 0.0, 4)

        if self._baseline:
            data.relative_dilation = round(self._ema - self._baseline, 4)

        # ---- brightness hint ----
        data.brightness_hint = self._brightness_hint(self._ema)

        # ---- gaze zone ----
        gz, gx, gy = self._gaze_zone(landmarks, frame_w, frame_h)
        data.gaze_zone = gz
        data.gaze_x    = round(gx, 3)
        data.gaze_y    = round(gy, 3)

        return data

    def reset_calibration(self) -> None:
        self._calib_buf.clear()
        self._baseline = None
        self._ema      = None
        log.info("Pupillometry calibration reset.")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _iris_diameter(
        landmarks, iris_indices: list[int], fw: int, fh: int
    ) -> float:
        """
        Estimate iris diameter in pixels from 5 iris landmarks.
        iris_indices layout: [centre, right, top, left, bottom]
        Diameter = mean of (right-left distance, bottom-top distance).
        """
        pts = [
            (landmarks[i].x * fw, landmarks[i].y * fh)
            for i in iris_indices
        ]
        # Horizontal span: right (idx 1) to left (idx 3)
        h_span = abs(pts[1][0] - pts[3][0])
        # Vertical span: top (idx 2) to bottom (idx 4)
        v_span = abs(pts[2][1] - pts[4][1])
        return (h_span + v_span) / 2.0

    def _brightness_hint(self, smoothed: float) -> str:
        if smoothed > self._dil_high:
            return "INCREASE"   # pupils dilated → dim environment → raise brightness
        if smoothed < self._dil_low:
            return "DECREASE"   # pupils constricted → bright env → lower brightness
        return "HOLD"

    def _gaze_zone(
        self, landmarks, fw: int, fh: int
    ) -> tuple[str, float, float]:
        """
        Estimate gaze direction from iris centre vs eye bounding box.
        Returns (zone_label, norm_gaze_x, norm_gaze_y).
        """
        # Use mean of both iris centres
        l_cx = landmarks[_LEFT_IRIS[0]].x
        l_cy = landmarks[_LEFT_IRIS[0]].y
        r_cx = landmarks[_RIGHT_IRIS[0]].x
        r_cy = landmarks[_RIGHT_IRIS[0]].y
        gaze_x = (l_cx + r_cx) / 2.0
        gaze_y = (l_cy + r_cy) / 2.0

        # Vertical zone
        if gaze_y < self._gz_top:
            zone = "Top"
        elif gaze_y > self._gz_bot:
            zone = "Bottom"
        else:
            zone = "Centre"

        return zone, gaze_x, gaze_y
