import logging

import cv2
import numpy as np

from frigate.camera import PTZMetrics
from frigate.config import MotionConfig
from frigate.motion import MotionDetector
from frigate.util.image import grab_cv2_contours

logger = logging.getLogger(__name__)


def _history_from_alpha(frame_alpha: float) -> int:
    """Derive MOG2 history length from frame_alpha (clamped to [50, 2000])."""
    return max(50, min(2000, int(1 / frame_alpha)))


class MoG2MotionDetector(MotionDetector):
    def __init__(
        self,
        frame_shape,
        config: MotionConfig,
        fps: int,
        ptz_metrics: PTZMetrics = None,
        name="mog2",
        blur_radius=1,
        interpolation=cv2.INTER_NEAREST,
        contrast_frame_history=50,
    ):
        self.name = name
        self.config = config
        self.frame_shape = frame_shape
        self.resize_factor = frame_shape[0] / config.frame_height
        self.motion_frame_size = (
            config.frame_height,
            config.frame_height * frame_shape[1] // frame_shape[0],
        )

        # MOG2 background subtractor with history derived from frame_alpha
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=_history_from_alpha(config.frame_alpha),
            varThreshold=config.threshold,
            detectShadows=True,
        )

        self.frame_counter = 0
        self.motion_frame_count = 0
        self.calibrating = True
        self.save_images = False
        self.interpolation = interpolation

        # Auto-scale contour_area relative to a 100px reference height.
        # At frame_height=100 this is 1.0x; at 300px it becomes 9.0x.
        self.scaled_contour_area = config.contour_area * (config.frame_height / 100) ** 2

        # Contrast adjustment tracking
        self.contrast_values = np.zeros((contrast_frame_history, 2), np.uint8)
        self.contrast_values[:, 1:2] = 255
        self.contrast_values_index = 0

        self.ptz_metrics = ptz_metrics
        self.last_stop_time = None

        self.update_mask()

    def is_calibrating(self):
        return self.calibrating

    def detect(self, frame):
        motion_boxes = []

        if not self.config.enabled:
            return motion_boxes

        # PTZ autotracking: motor moving — return full-frame box
        if (
            self.ptz_metrics.autotracker_enabled.value
            and not self.ptz_metrics.motor_stopped.is_set()
        ):
            return [
                (
                    int(self.frame_shape[1] * 0.1),
                    int(self.frame_shape[0] * 0.1),
                    int(self.frame_shape[1] * 0.9),
                    int(self.frame_shape[0] * 0.9),
                )
            ]

        gray = frame[0 : self.frame_shape[0], 0 : self.frame_shape[1]]

        resized_frame = cv2.resize(
            gray,
            dsize=(self.motion_frame_size[1], self.motion_frame_size[0]),
            interpolation=self.interpolation,
        )

        if self.save_images:
            resized_saved = resized_frame.copy()

        # Contrast improvement: normalize per-channel before feeding MOG2
        if self.config.improve_contrast:
            min_value = np.percentile(resized_frame, 4).astype(np.uint8)
            max_value = np.percentile(resized_frame, 96).astype(np.uint8)
            if min_value < max_value:
                self.contrast_values[self.contrast_values_index] = [
                    min_value,
                    max_value,
                ]
                self.contrast_values_index = (self.contrast_values_index + 1) % len(
                    self.contrast_values
                )
                avg_min, avg_max = np.mean(self.contrast_values, axis=0)
                resized_frame = np.clip(resized_frame, avg_min, avg_max)
                resized_frame = (
                    ((resized_frame - avg_min) / (avg_max - avg_min)) * 255
                ).astype(np.uint8)

        # Apply background subtraction
        # Use fast learning rate during calibration then switch to the algorithm
        learning_rate = (
            self.config.delta_alpha if self.calibrating else -1
        )
        fg_mask = self.bg_subtractor.apply(resized_frame, learningRate=learning_rate)

        # Suppress near-white regions (headlights, reflections) from motion mask
        white_mask = (resized_frame > 225).astype(np.uint8) * 255
        fg_mask[white_mask == 255] = 0

        # Apply spatial mask
        fg_mask[self.mask] = 0

        # Threshold at 254 to exclude MOG2 shadow pixels (127) cleanly
        thresh = cv2.threshold(fg_mask, 254, 255, cv2.THRESH_BINARY)[1]

        # Morphological cleanup: open to remove noise, close to fill holes
        kernel = np.ones((2, 2), np.uint8)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)

        contours = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = grab_cv2_contours(contours)

        # Sort largest first, cap at 10 to bound processing
        contours = sorted(contours, key=cv2.contourArea, reverse=True)

        total_contour_area = 0
        for c in contours[:10]:
            contour_area = cv2.contourArea(c)
            total_contour_area += contour_area
            if contour_area > self.scaled_contour_area:
                x, y, w, h = cv2.boundingRect(c)
                motion_boxes.append(
                    (
                        int(x * self.resize_factor),
                        int(y * self.resize_factor),
                        int((x + w) * self.resize_factor),
                        int((y + h) * self.resize_factor),
                    )
                )

        pct_motion = total_contour_area / (
            self.motion_frame_size[0] * self.motion_frame_size[1]
        )

        # Scene change / skip_motion_threshold — suppress and recalibrate
        if (
            hasattr(self.config, "skip_motion_threshold")
            and self.config.skip_motion_threshold is not None
            and pct_motion > self.config.skip_motion_threshold
        ):
            self.calibrating = True
            return []

        # Cap boxes during overwhelming motion (rain, lightning, IR switch)
        if pct_motion > self.config.lightning_threshold:
            motion_boxes = motion_boxes[:4]
            self.calibrating = True

        # PTZ motor just stopped — reset background model to new scene
        if (
            self.ptz_metrics.autotracker_enabled.value
            and self.ptz_metrics.motor_stopped.is_set()
            and self.ptz_metrics.stop_time.value != 0
            and (
                self.last_stop_time is None
                or self.ptz_metrics.stop_time.value != self.last_stop_time
            )
        ):
            self.last_stop_time = self.ptz_metrics.stop_time.value
            self.bg_subtractor.setHistory(1)
            motion_boxes = []
            pct_motion = 0

        # Clear calibrating flag once scene settles
        if pct_motion < 0.05 and len(motion_boxes) <= 4:
            self.calibrating = False

        if self.save_images:
            thresh_vis = cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR)
            for b in motion_boxes:
                cv2.rectangle(
                    thresh_vis,
                    (int(b[0] / self.resize_factor), int(b[1] / self.resize_factor)),
                    (int(b[2] / self.resize_factor), int(b[3] / self.resize_factor)),
                    (0, 0, 255),
                    2,
                )
            frames = [
                resized_saved,
                cv2.cvtColor(fg_mask, cv2.COLOR_GRAY2BGR),
                cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR),
                thresh_vis,
            ]
            cv2.imwrite(
                f"debug/frames/{self.name}-{self.frame_counter}.jpg",
                (
                    cv2.hconcat(frames)
                    if self.frame_shape[0] > self.frame_shape[1]
                    else cv2.vconcat(frames)
                ),
            )

        if self.save_images or self.calibrating:
            self.frame_counter += 1

        return motion_boxes

    def update_mask(self) -> None:
        resized_mask = cv2.resize(
            self.config.mask,
            dsize=(self.motion_frame_size[1], self.motion_frame_size[0]),
            interpolation=cv2.INTER_AREA,
        )
        self.mask = np.where(resized_mask == [0])

        # Reset background model when mask changes so it relearns the new scene
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=_history_from_alpha(self.config.frame_alpha),
            varThreshold=self.config.threshold,
            detectShadows=True,
        )
        self.calibrating = True
        self.motion_frame_count = 0

    def stop(self) -> None:
        """Stop the motion detector."""
        pass
