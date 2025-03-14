from typing import Tuple

from frigate.config import MotionConfig

from .improved_motion import ImprovedMotionDetector
from .mog2_motion import MoG2Detector 


# Add a facotry function that can instantiate different motion detectors based on configs
def motionFactory(
    frame_shape: Tuple[int, int, int],
    config: MotionConfig,
    fps: int,
    name="factory",
    ptz_metrics=None,
):
    methods = {
        config.method.improved: ImprovedMotionDetector,
        config.method.mog2: MoG2Detector,
    }
    # return the motion class from the array above, defaulting to
    # improved_motion if there are any issues
    return methods.get(config.method, ImprovedMotionDetector)(
        frame_shape, config, fps, name=name, ptz_metrics=ptz_metrics
    )
