from typing import Tuple

from frigate.config import MotionConfig
from frigate.motion.improved_motion import ImprovedMotionDetector
from frigate.motion.mog2_motion import MoG2MotionDetector


def create_motion_detector(
    frame_shape: Tuple[int, int, int],
    config: MotionConfig,
    fps: int,
    name: str = "unknown",
    ptz_metrics=None,
):
    """Factory function to instantiate the configured motion detector."""
    methods = {
        "improved": ImprovedMotionDetector,
        "mog2": MoG2MotionDetector,
    }
    detector_class = methods.get(config.method.value, ImprovedMotionDetector)
    return detector_class(frame_shape, config, fps, name=name, ptz_metrics=ptz_metrics)
