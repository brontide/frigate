import logging
import cv2
import imutils
import numpy as np
from frigate.camera import PTZMetrics
from frigate.comms.config_updater import ConfigSubscriber
from frigate.config import MotionConfig
from frigate.motion import MotionDetector

logger = logging.getLogger(__name__)

class MoG2Detector(MotionDetector):
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
        # Initialize basic instance variables
        self.name = name
        self.config = config
        self.frame_shape = frame_shape
        self.resize_factor = frame_shape[0] / config.frame_height
        
        # Calculate motion frame dimensions
        self.motion_frame_size = (
            config.frame_height,
            config.frame_height * frame_shape[1] // frame_shape[0],
        )
        
        # Initialize KNN background subtractor
        #self.bg_subtractor = cv2.createBackgroundSubtractorKNN(
        #    history=1000,           # Length of history to keep
        #    dist2Threshold=100.0,  # Threshold for background/foreground distinction
        #    detectShadows=True    # Disable shadow detection for simpler processing
        #)
        
        # Initialize MOG2 background subtractor (no shadow detection)
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=600,          # Number of frames to build model
            varThreshold=14,      # Sensitivity to change
            detectShadows=True    # Disable shadow detection
        )

        # Counters and flags
        self.frame_counter = 0
        self.calibrating = True
        
        resized_mask = cv2.resize(
            config.mask,
            dsize=(self.motion_frame_size[1], self.motion_frame_size[0]),
            interpolation=cv2.INTER_LINEAR,
        )
        self.mask = np.where(resized_mask == [0])
        
        # Image processing parameters
        self.save_images = False
        self.interpolation = interpolation

        # Contrast adjustment tracking
        self.contrast_values = np.zeros((contrast_frame_history, 2), np.uint8)
        self.contrast_values[:, 1:2] = 255
        self.contrast_values_index = 0
        
        # External connections
        self.config_subscriber = ConfigSubscriber(f"config/motion/{name}", True)
        self.ptz_metrics = ptz_metrics
        self.last_stop_time = None

    def is_calibrating(self):
        return False # self.calibrating

    def detect(self, frame):
        motion_boxes = []

        # Check for config updates
        _, updated_config = self.config_subscriber.check_for_update()
        if updated_config:
            self.config = updated_config

        if not self.config.enabled:
            return motion_boxes

        # Handle PTZ autotracking case
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
        # Use full color frame
        color_frame = frame[0:self.frame_shape[0], 0:self.frame_shape[1]]
        
        # Resize frame maintaining color
        resized_frame = cv2.resize(
            color_frame,
            dsize=(self.motion_frame_size[1], self.motion_frame_size[0]),
            interpolation=self.interpolation,
        )

        # Convert to grayscale for intensity analysis
        frame_gray = resized_frame.copy()

        if self.save_images:
            resized_saved = resized_frame.copy()

        # Apply contrast improvement if enabled
        if self.config.improve_contrast and False:
            min_value = np.percentile(resized_frame, 4).astype(np.uint8)
            max_value = np.percentile(resized_frame, 96).astype(np.uint8)
            if min_value < max_value:
                self.contrast_values[self.contrast_values_index] = [min_value, max_value]
                self.contrast_values_index = (self.contrast_values_index + 1) % len(self.contrast_values)
                avg_min, avg_max = np.mean(self.contrast_values, axis=0)
                resized_frame = np.clip(resized_frame, avg_min, avg_max)
                resized_frame = (
                    ((resized_frame - avg_min) / (avg_max - avg_min)) * 255
                ).astype(np.uint8)

        if self.save_images:
            contrasted_saved = resized_frame.copy()


        # Apply background subtraction
        fg_mask = self.bg_subtractor.apply(resized_frame, learningRate=0.005)

        # Subtract near-white regions from the motion mask
        white_mask = cv2.threshold(frame_gray, 225, 255, cv2.THRESH_BINARY)[1]  # Pure/near-white areas
        fg_mask[white_mask == 255] = 0  # Remove white regions from motion
        # Apply motion mask
        fg_mask[self.mask] = 0
        
        # Threshold and dilate
        thresh = cv2.threshold(fg_mask, 254, 255, cv2.THRESH_BINARY)[1]
        kernel = np.ones((2, 2), np.uint8)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
 
        # Find contours
        contours = cv2.findContours(
            thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        contours = imutils.grab_contours(contours)

        # Sort contours by area (largest to smallest)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)

        # Process contours
        total_contour_area = 0
        for c in contours[:10]:
            contour_area = cv2.contourArea(c)
            total_contour_area += contour_area
            if contour_area > self.config.contour_area:
                x, y, w, h = cv2.boundingRect(c)
                motion_boxes.append(
                    (
                        int(x * self.resize_factor),
                        int(y * self.resize_factor),
                        int((x + w) * self.resize_factor),
                        int((y + h) * self.resize_factor),
                    )
                )

        # Calculate motion percentage
        pct_motion = total_contour_area / (self.motion_frame_size[0] * self.motion_frame_size[1])

        # if we are overwhelemed with motion 
        if pct_motion > .4:
            motion_boxes = motion_boxes[:4]

        # Handle PTZ stop condition
        # FIXME: Unable to test this condition so I'm speculating.
        if (
            self.ptz_metrics.autotracker_enabled.value
            and self.ptz_metrics.motor_stopped.is_set()
            and self.ptz_metrics.stop_time.value != 0
            and (self.last_stop_time is None or self.ptz_metrics.stop_time.value != self.last_stop_time)
        ):
            self.last_stop_time = self.ptz_metrics.stop_time.value
            # reset the history on subtractor
            self.bg_subtractor.setHistory(1)
            motion_boxes = []
            pct_motion = 0

        return motion_boxes

    def stop(self) -> None:
        """Stop the motion detector."""
        self.config_subscriber.stop()
