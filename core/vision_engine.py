"""
Vision Engine — captures webcam frames and runs MediaPipe FaceMesh.
Detects blinks (EAR), screen distance, head-posture, pupil dilation,
and gaze zone. Runs in its own daemon thread; updates a shared VisionState.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

import cv2

from utils.config import get_config
from utils.logger import setup_logger

log = setup_logger("vision_engine")


@dataclass
class VisionState:
    """Thread-safe snapshot of the latest vision readings."""

    blink_count: int = 0
    blink_rate_per_min: float = 0.0
    last_blink_time: float = field(default_factory=time.time)
    ear: float = 1.0

    distance_cm: float = 60.0
    face_detected: bool = False

    head_offset_x: float = 0.0
    head_offset_y: float = 0.0
    posture_alert: bool = False

    # ---- Pupillometry fields ----
    pupil_ratio: float = 0.0           # raw normalised iris/face ratio
    pupil_smoothed: float = 0.0        # EMA-smoothed ratio
    pupil_diameter_px: float = 0.0     # avg iris diameter in pixels
    relative_dilation: float = 0.0     # deviation from calibrated baseline
    pupil_calibrated: bool = False
    brightness_hint: str = "HOLD"      # INCREASE | DECREASE | HOLD

    # ---- Gaze fields ----
    gaze_zone: str = "Centre"          # Top | Centre | Bottom
    gaze_x: float = 0.5
    gaze_y: float = 0.5

    frame_rgb: object = None           # latest annotated BGR numpy array
    running: bool = False
    error: str | None = None

    _lock: threading.Lock = field(default_factory=threading.Lock)

    def update(self, **kwargs) -> None:
        with self._lock:
            for k, v in kwargs.items():
                setattr(self, k, v)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                k: v
                for k, v in self.__dict__.items()
                if not k.startswith("_") and k != "frame_rgb"
            }


class VisionEngine(threading.Thread):
    """Background thread: webcam → MediaPipe → VisionState updates."""

    # MediaPipe FaceMesh landmark indices
    _LEFT_EYE  = [362, 385, 387, 263, 373, 380]
    _RIGHT_EYE = [33,  160, 158, 133, 153, 144]
    _LEFT_CHEEK  = 234
    _RIGHT_CHEEK = 454
    _NOSE_TIP = 1

    # Iris landmarks (refined model)
    _LEFT_IRIS  = [468, 469, 470, 471, 472]
    _RIGHT_IRIS = [473, 474, 475, 476, 477]

    def __init__(self, state: VisionState) -> None:
        super().__init__(daemon=True, name="VisionEngine")
        self.state = state
        self._stop_event = threading.Event()
        cfg = get_config()
        self._cam_cfg   = cfg.camera
        self._blink_cfg = cfg.blink
        self._dist_cfg  = cfg.distance
        self._pupil_enabled = bool(cfg.pupillometry.get("enabled", True))

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        try:
            import mediapipe as mp
            import numpy as np
        except ImportError as e:
            self.state.update(error=str(e))
            log.error("Missing dependency: %s", e)
            return

        # Conditionally import pupillometry engine
        pupil_engine = None
        if self._pupil_enabled:
            try:
                from core.pupillometry import PupillometryEngine
                pupil_engine = PupillometryEngine()
                log.info("Pupillometry engine active.")
            except Exception as e:
                log.warning("Pupillometry engine failed to init: %s", e)

        mp_face_mesh = mp.solutions.face_mesh
        face_mesh = mp_face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,          # required for iris landmarks
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

        cap = cv2.VideoCapture(self._cam_cfg["device_index"], cv2.CAP_ANY)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self._cam_cfg["resolution_width"])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._cam_cfg["resolution_height"])
        cap.set(cv2.CAP_PROP_FPS,          self._cam_cfg["fps"])

        if not cap.isOpened():
            self.state.update(error="Could not open webcam.")
            log.error("Could not open webcam at index %s", self._cam_cfg["device_index"])
            return

        self.state.update(running=True)
        log.info("Vision engine started.")

        ear_thresh   = self._blink_cfg["ear_threshold"]
        consec_req   = self._blink_cfg["ear_consecutive_frames"]
        focal_len    = self._dist_cfg["focal_length_px"]
        face_w_cm    = self._dist_cfg["avg_face_width_cm"]
        posture_thr  = self._dist_cfg.get("forward_head_threshold", 0.15)

        frame_below  = 0
        blink_count  = 0
        blink_times: list[float] = []

        while not self._stop_event.is_set():
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.05)
                continue

            h, w = frame.shape[:2]
            results = face_mesh.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            annotated = frame.copy()

            if results.multi_face_landmarks:
                lm = results.multi_face_landmarks[0].landmark

                # --- Blink (EAR) ---
                ear = self._avg_ear(lm, w, h)
                if ear < ear_thresh:
                    frame_below += 1
                else:
                    if frame_below >= consec_req:
                        blink_count += 1
                        now = time.time()
                        blink_times.append(now)
                        blink_times = [t for t in blink_times if now - t <= 60]
                        self.state.update(
                            blink_count=blink_count,
                            blink_rate_per_min=float(len(blink_times)),
                            last_blink_time=now,
                        )
                    frame_below = 0

                # --- Distance ---
                lx = int(lm[self._LEFT_CHEEK].x  * w)
                rx = int(lm[self._RIGHT_CHEEK].x * w)
                face_px = abs(rx - lx)
                dist_cm = (face_w_cm * focal_len / face_px) if face_px > 0 else 60.0

                # --- Posture ---
                head_off = abs(lm[self._NOSE_TIP].y - 0.35)
                posture_alert = head_off > posture_thr

                self.state.update(
                    face_detected=True,
                    distance_cm=round(dist_cm, 1),
                    head_offset_y=round(head_off, 3),
                    posture_alert=posture_alert,
                    ear=round(ear, 3),
                )

                # --- Pupillometry + Gaze ---
                if pupil_engine is not None:
                    try:
                        pd = pupil_engine.process(lm, w, h)
                        self.state.update(
                            pupil_ratio=pd.pupil_ratio,
                            pupil_smoothed=pd.smoothed_ratio,
                            pupil_diameter_px=pd.avg_diameter_px,
                            relative_dilation=pd.relative_dilation,
                            pupil_calibrated=pd.is_calibrated,
                            brightness_hint=pd.brightness_hint,
                            gaze_zone=pd.gaze_zone,
                            gaze_x=pd.gaze_x,
                            gaze_y=pd.gaze_y,
                        )
                        # Draw iris circles on annotated frame
                        self._draw_iris(annotated, lm, w, h)
                        # Draw gaze indicator
                        self._draw_gaze_hud(annotated, pd, w, h)
                    except Exception as e:
                        log.debug("Pupillometry frame error: %s", e)

                # Draw standard HUD
                cv2.putText(annotated, f"EAR:{ear:.2f}  Blinks:{blink_count}",
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 1)
                cv2.putText(annotated, f"Dist:{dist_cm:.0f}cm",
                            (10, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 200, 0), 1)
                if posture_alert:
                    cv2.putText(annotated, "POSTURE ALERT",
                                (10, 74), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

                self.state.update(frame_rgb=annotated)
            else:
                self.state.update(face_detected=False, frame_rgb=annotated)

        cap.release()
        face_mesh.close()
        self.state.update(running=False)
        log.info("Vision engine stopped.")

    # ------------------------------------------------------------------
    # Iris drawing helpers
    # ------------------------------------------------------------------

    def _draw_iris(self, frame, lm, w: int, h: int) -> None:
        """Draw green iris circles on annotated frame."""
        for iris_pts in (self._LEFT_IRIS, self._RIGHT_IRIS):
            cx = int(lm[iris_pts[0]].x * w)
            cy = int(lm[iris_pts[0]].y * h)
            # Estimate radius from horizontal span / 2
            r_px = int(abs(lm[iris_pts[1]].x * w - lm[iris_pts[3]].x * w) / 2)
            if r_px > 1:
                cv2.circle(frame, (cx, cy), r_px, (0, 220, 255), 1)
                cv2.circle(frame, (cx, cy), 2,    (0, 220, 255), -1)

    @staticmethod
    def _draw_gaze_hud(frame, pd, w: int, h: int) -> None:
        """Draw brightness hint and gaze zone label on frame."""
        hint_color = {
            "INCREASE": (0, 255, 128),
            "DECREASE": (0, 128, 255),
            "HOLD":     (180, 180, 180),
        }.get(pd.brightness_hint, (255, 255, 255))

        calib_txt = (
            f"Pupil:{pd.smoothed_ratio:.3f}"
            if pd.is_calibrated
            else f"Calibrating…  {pd.smoothed_ratio:.3f}"
        )
        cv2.putText(frame, calib_txt,
                    (10, h - 56), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (200, 200, 200), 1)

        brightness_txt = f"Bright hint: {pd.brightness_hint}"
        cv2.putText(frame, brightness_txt,
                    (10, h - 36), cv2.FONT_HERSHEY_SIMPLEX, 0.48, hint_color, 1)

        gaze_txt = f"Gaze: {pd.gaze_zone}"
        cv2.putText(frame, gaze_txt,
                    (10, h - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (200, 200, 200), 1)

    # ------------------------------------------------------------------
    # EAR helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ear_for_eye(landmarks, indices: list[int], w: int, h: int) -> float:
        import numpy as np
        pts = [(landmarks[i].x * w, landmarks[i].y * h) for i in indices]
        A = np.linalg.norm(np.array(pts[1]) - np.array(pts[5]))
        B = np.linalg.norm(np.array(pts[2]) - np.array(pts[4]))
        C = np.linalg.norm(np.array(pts[0]) - np.array(pts[3]))
        return (A + B) / (2.0 * C) if C > 0 else 0.0

    def _avg_ear(self, lm, w: int, h: int) -> float:
        return (
            self._ear_for_eye(lm, self._LEFT_EYE, w, h)
            + self._ear_for_eye(lm, self._RIGHT_EYE, w, h)
        ) / 2.0
